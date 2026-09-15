# Tasks — HU-F3.1 Login con `email` + `password`

> **Phase**: tasks (sdd-tasks) · **Status**: ready for sdd-apply
> **HU ID**: HU-F3.1 (Fase 3 — primera HU; Autenticación y turno de caja, transversal a todas las CU operativas)
> **Working dir**: `E:\easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `ba9d81a`, Fase 2 cerrada 2026-09-15 con F2.1 + F2.2 + F2.3 archivados)
> **Cross-refs**: `exploration.md` §6-§17, `proposal.md` §5-§17, `design.md` §5-§15 + Appendix A + Appendix B, `specs/operations/spec.md` (DELTA con 7 new REQ-OPS-106..112)
> **Prereq change**: `hu-f2-3-electron-auto-update-kiosko` archived 2026-09-15
> **Author**: Parkos Dev <dev@parkos.local> · **Language**: español neutro profesional

---

## §0. Metadata

| Campo | Valor |
|---|---|
| **Change** | `hu-f3-1-login-email-password` |
| **HU** | F3.1 — Login con `email` + `password` contra POST /auth/login con `credentials:'include'` + cookie `parkos_session` (httponly+secure+samesite=lax) + hidratación de `authStore` desde GET /auth/me + redirect transaccional a `/` + anti-enumeración (401 → `errors.invalidCredentials` único) + WCAG 2.1 AA compliance axe-core |
| **Owner** | Parkos Dev <dev@parkos.local> |
| **Working tree** | `E:\easypunto_parkos` |
| **Branch base** | `feat/fase-2-electron-scaffold` (F2.1 + F2.2 + F2.3 archivados) |
| **PR target** | `origin/dev` |
| **Total tasks** | 4 atomic (T1..T4) |
| **Total clusters** | 1 (C1 — login flow end-to-end) |
| **Production LOC budget** | ~190 LOC (production 170 + configs 10 + JSDoc 10) |
| **Test LOC budget** | ~240 LOC (unit 160 + e2e 80) |
| **Total LOC budget** | ~430 LOC |
| **Atomic commits** | 4 (C1: T1, T2, T3, T4) |
| **Review actor** | `sdd-verify` post-apply |
| **Archive actor** | orchestrator (post-verify PASS) |
| **Related artifacts** | `exploration.md` (17 secciones, 10 DEC-F3.1-01..10, 8 riesgos R1..R8) · `proposal.md` (16 secciones, 11 DEC-F3.1-01..11 ratified, 7 new REQ-OPS-106..112) · `design.md` (15 secciones + 2 apéndices, 8 TS mockups + 3 configs delta) · `specs/operations/spec.md` (DELTA con 7 new REQ-OPS-106..112 user-facing per F1.15 precedent) |
| **Scope** | Primer consumer end-to-end real de las primitivas de Fase 2 (parkosFetch + authStore + useAuth + bridge IPC + shadcn Form). Login form (RHF+Zod) + POST /auth/login con credentials:'include' + hidratación authStore + redirect transaccional + axe-core WCAG 2.1 AA. NO incluye lockout countdown UI (F3.2), refresh pre-flight (F3.2), logout UI (F3.3+), AuthGuard (F3.3+), backend cambios (HU-F1.2 shipped). |
| **Dependencies** | F2.1 archivado (Electron scaffold) · F2.2 archivado (bridge IPC + parkosFetch + authStore + useAuth SWR) · F2.3 archivado (StatusBar + kiosko + api-status) · HU-F1.2 shipped Fase 1 (POST /auth/login + GET /auth/me backend) · npm 11.16.0 local Windows + npm sandbox F.6 caveat documentado |

---

## §1. Resumen ejecutivo

| Métrica | Valor |
|---|---|
| Total LOC production | ~190 |
| Total LOC tests | ~240 |
| Total LOC delta | ~430 |
| Atomic tasks | 4 (T1..T4) |
| Clusters | 1 (C1) end-to-end |
| Acceptance gates | 7 (G1..G6 + G7 implícito axe-core WCAG 2.1 AA) |
| DEC-F3.1-NN ratificadas | 11 (DEC-F3.1-01..11) |
| New REQ-OPS | 7 (REQ-OPS-106..112) |
| Files NEW | 7 (~410 LOC production + tests) |
| Files MODIFY | 3 (~10 LOC delta + 5 keys i18n) |
| Files READ ONLY | 16 (Fase 2 primitives + backend anchors) |
| Conventional commits | feat(auth) × 2 + feat(router) × 1 + test(electron) × 1 |
| Author commits | `Parkos Dev <dev@parkos.local>` (sin Co-authored-by, sin AI trailers) |
| Sandbox F.6 caveat | npm 11.16.0 refuses workspace:* → e2e G6 SKIPPED local; CI matrix required |

**Plan 190 LOC matches**: 170 production + 20 JSDoc/configs = ~190 verbatim `plan.md:1297` + `proposal.md §1` + `exploration.md §10.5`.

**No-paralelización intra-cluster** (cross-ref design §4):

- T1 antes de T2: T1 provee Login + LoginForm declarativos sin API integration. T2 integra `postLogin` en `onSubmit` de T1.
- T2 antes de T3: T3 agrega `useEffect` redirect post-`setTokens` (T2 setea tokens via `useAuthStore.setTokens`).
- T3 antes de T4: T4 (e2e) requiere Login.tsx completo (route + form + api + redirect).
- Single cluster C1 end-to-end con orden interno estricto T1 → T2 → T3 → T4 (no negociable).

**Dependencias** (estrictas, no negociables):

```
T1 (Login + LoginForm + RHF+Zod)
  │
  └─► T2 (postLogin + credentials:'include' + error mapping + setTokens)
       │
       └─► T3 (useEffect redirect + App.tsx Route /login)
            │
            └─► T4 (e2e login.spec.ts — 3 scenarios + axe-core)
```

---

## §2. Dependency graph + Cluster ordering

### §2.1 Diagrama ASCII

```
                    ┌─────────────────────────────────────────────┐
                    │ FEATURE FOLDER (NEW — DEC-F3.1-01)         │
                    │ apps/electron-sucursal/src/features/auth/   │
                    └─────────────────────────────────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
   ┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────────────┐
   │ T1 LoginForm        │  │ T1 Login.tsx        │  │ T1 loginSchema.ts    │
   │ (presentational)    │  │ (container base)    │  │ (Zod local)          │
   │ ~60 LOC prod        │  │ ~60 LOC prod (base) │  │ ~10 LOC prod         │
   │ + 30 LOC tests      │  │ + 50 LOC tests      │  │ (en T1)              │
   └─────────────────────┘  └─────────────────────┘  └──────────────────────┘
              │                        │                        │
              └────────┬───────────────┴────────────────────────┘
                       │
                       ▼
              ┌─────────────────────────────────────┐
              │ T1 commit — feat(auth)              │
              │ + 5 i18n validation keys            │
              └─────────────────────────────────────┘
                       │
                       ▼
              ┌─────────────────────────────────────┐
              │ T2 loginApi.ts (NEW ~30 LOC)        │
              │ + Login.tsx MODIFY (+5 LOC)         │
              │ postLogin + credentials:'include'   │
              │ + InvalidCredentialsError           │
              │ + AccountLockedError                │
              └─────────────────────────────────────┘
                       │
                       ▼
              ┌─────────────────────────────────────┐
              │ T2 commit — feat(auth)              │
              │ postLogin wirea setTokens           │
              └─────────────────────────────────────┘
                       │
                       ▼
              ┌─────────────────────────────────────┐
              │ T3 Login.tsx MODIFY (+10 LOC)       │
              │ useEffect[isAuth,data.user,loading] │
              │ App.tsx MODIFY (+5 LOC)             │
              │ <Route path="/login">              │
              └─────────────────────────────────────┘
                       │
                       ▼
              ┌─────────────────────────────────────┐
              │ T3 commit — feat(router)            │
              │ redirect transaccional             │
              └─────────────────────────────────────┘
                       │
                       ▼
              ┌─────────────────────────────────────┐
              │ T4 e2e/auth/login.spec.ts (NEW)     │
              │ 3 scenarios + axe-core              │
              └─────────────────────────────────────┘
                       │
                       ▼
              ┌─────────────────────────────────────┐
              │ T4 commit — test(electron)          │
              │ 3 e2e + axe-core                   │
              └─────────────────────────────────────┘
```

### §2.2 Tabla de orden estricto

| Step | Cluster | Task | Cuándo | Acción | Razón orden |
|---|---|---|---|---|---|
| 1 | C1 | **T1** | primera | NEW `LoginForm.tsx` + `Login.tsx` + `loginSchema.tsx` + MODIFY `auth.json` (+5 keys) | DEC-F3.1-01/02/06: feature folder + Container/Presentational split + Zod local. Login + LoginForm declarativos sin API integration. |
| 2 | C1 | **T2** | después T1 | NEW `loginApi.ts` + `loginApi.test.ts` + MODIFY `Login.tsx` (+5 LOC) | DEC-F3.1-03/04/05: credentials:'include' + fetch raw + custom error mapping. Integra `postLogin` en `onSubmit` de T1. |
| 3 | C1 | **T3** | después T2 | MODIFY `Login.tsx` (+10 LOC useEffect) + `App.tsx` (+5 LOC route) + MODIFY `Login.test.tsx` (+30 LOC) | DEC-F3.1-07: redirect transaccional post-`data.user` resuelto. |
| 4 | C1 | **T4** | después T3 | NEW `e2e/auth/login.spec.ts` (~80 LOC — 3 scenarios + axe-core) | e2e requiere Login.tsx completo (route + form + api + redirect). Plan.md:1295 verbatim. Sandbox F.6 SKIPPED-env (deviation D-env documentada). |

### §2.3 Justificación de orden

- **T1 antes que T2**: T2 (`loginApi.ts` + integration en `onSubmit`) depende de T1 (`Login.tsx` con `form.handleSubmit` + `LoginForm` presentacional). T2 wirea el `postLogin(...)` en el `onSubmit` que T1 declara pero no implementa.
- **T2 antes que T3**: T3 (`useEffect` redirect) depende de T2 (`useAuthStore.setTokens` post-`postLogin` 200 OK). El redirect se dispara cuando `useAuth().data.user` resuelve, que ocurre porque `setTokens` mutó el state que `useAuth()` SWR observa.
- **T3 antes que T4**: T4 (e2e `login.spec.ts`) requiere Login.tsx completo con route + form + api + redirect. T3 es la última pieza del container que permite que `await page.waitForURL('/')` funcione.
- **Single cluster C1 end-to-end**: la atomicidad del feature (login → setTokens → /auth/me → redirect) requiere que los 4 tasks se commiteen en orden sin pasos intermedios. Plan.md:1289 verbatim: "Login (page, contenedor: RHF+Zod, llama parkosFetch); LoginForm (presentacional, dos campos + botón)" — el flujo NO es divisible en features independientes.
- **Ningún task puede saltarse pasos** sin invalidar acceptance gates (cross-ref §8 G1..G6).

---

## §3. Cluster C1 — Login flow end-to-end (T1+T2+T3+T4)

### §3.0 Pre-requisitos C1

- branch: `feat/fase-2-electron-scaffold` checked out.
- working tree: `clean` (`git status --short` retorna vacío).
- pre-flight local:
  - `git log --oneline -1` → debe ser `ba9d81a` o posterior (F2.3 archivado 2026-09-15).
  - F2.1 archivado en `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/`.
  - F2.2 archivado en `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/`.
  - F2.3 archivado en `openspec/changes/archive/2026-09-15-hu-f2-3-electron-auto-update-kiosko/`.
  - `react-hook-form@^7.53.0` + `zod@^3.23.8` + `@hookform/resolvers@^3.9.0` en `apps/electron-sucursal/package.json:23, 45, 51` (F2.1 baseline).
  - `@radix-ui/react-label@^2.1.0` + `react-router-dom@^6.27.0` en `package.json:27, 47` (F2.1 baseline).
  - `@parkos/ui-kit/hooks` + `@parkos/ui-kit/store` subpath exports disponibles (F2.2 shippeó).
  - HU-F1.2 shipped backend `POST /auth/login` + `GET /auth/me` (`backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-583`).

### §3.1 Task T1 — Login page (container) + LoginForm (presentational) + loginSchema (Zod)

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done (apply 2026-09-15, commit 8961303) |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~200 LOC delta) |
| **Order** | 1 (primera de C1) |
| **Cluster** | C1 |
| **Pre-requisitos** | F2.1 + F2.2 + F2.3 archivados; RHF + Zod + resolvers ya en deps |
| **Acceptance gates** | G1 (RHF+Zod valida email formato + password min 8 con messages inline), G2 (401 → `t('invalidCredentials')` único) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- NEW: `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (~60 LOC — presentational puro, recibe `{form, onSubmit, isSubmitting, error}` via props).
- NEW: `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` (~30 LOC — render presentacional + axe-core 0 violaciones).
- NEW: `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (~60 LOC base — container con RHF + Zod resolver + useTranslation + useNavigate; placeholder `onSubmit` que NO llama fetch todavía).
- NEW: `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (~50 LOC base — vitest + @testing-library/react, render `<LoginForm>` stub + submit stub sin postLogin todavía).
- NEW: `apps/electron-sucursal/src/features/auth/api/loginSchema.ts` (~10 LOC — `loginSchema` Zod + `LoginInput` type export).
- MODIFY: `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (+5 validation keys sub-objeto `validation`).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, ~80 LOC):
   - Test U6 (`LoginForm.test.tsx`): render presentacional con form mockeado via `FormProvider` → `screen.getByTestId('login-email')` + `login-password` + `login-submit` visibles.
   - Test U7 (`LoginForm.test.tsx`): error `invalid_credentials` prop → `<p role="alert" data-testid="login-error-invalid">` renderiza texto `t('invalidCredentials')`.
   - Test U8 (`LoginForm.test.tsx`): `expect(await axe(container)).toHaveNoViolations()` — axe-core 0 violaciones WCAG 2.1 AA.
   - Test U11 (`Login.test.tsx`): fill `email = 'not-an-email'` + click submit → `fetch` NOT called + `<FormMessage>` muestra `validation.email.invalid`.
   - Test U12 (`Login.test.tsx`): fill `password = 'short'` + click submit → `fetch` NOT called + `<FormMessage>` muestra `validation.password.minLength`.
   - Test U4 (transversal): snapshot test `auth.json` con 5 nuevas validation keys.

2. **GREEN** (implementación mínima, ~130 LOC):
   - `loginSchema.ts` (~10 LOC): `z.object({email: z.string().min(1).email(), password: z.string().min(1).min(8)})` con messages como KEYS i18n.
   - `Login.tsx` (~60 LOC): `useForm<LoginInput>({resolver: zodResolver(loginSchema), mode:'onBlur', defaultValues: {email:'', password:''}})` + `<LoginForm form={form} onSubmit={onSubmit} isSubmitting={formState.isSubmitting} error={errorState} />`. `onSubmit` placeholder que setea `errorState = null` (T2 wirea `postLogin`).
   - `LoginForm.tsx` (~60 LOC): shadcn `Form/FormField/FormItem/FormLabel/FormControl/FormMessage` + `Input` con `autoComplete="username"/"current-password"` + `inputMode="email"` + `data-testid="login-email"/"login-password"`. `<Button type="submit" disabled={isSubmitting}>` con texto `t('submit')` o `t('common:loading')`. 3 condicionales `error?.kind` para `<p role="alert">` mensajes.
   - `auth.json` delta (~5 keys nuevas): `"validation": {required, email:{invalid}, password:{minLength, required}}`.

3. **REFACTOR** (extract constants, JSDoc):
   - Constante `EMAIL_TESTID = 'login-email'` + `PASSWORD_TESTID = 'login-password'` + `SUBMIT_TESTID = 'login-submit'` + `INVALID_TESTID = 'login-error-invalid'` + `LOCKOUT_TESTID = 'login-error-lockout'` + `NETWORK_TESTID = 'login-error-network'`.
   - JSDoc cross-ref DEC-F3.1-02/06 en `LoginForm` y `LoginSchema`.
   - Helper `getErrorMessage(errorKind, t)` extraído.

**Commit message**:

```
feat(auth): adicionar Login page con RHF+Zod (email/password) + LoginForm presentacional + 5 i18n validation keys
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm vitest run src/features/auth/components/LoginForm.test.tsx src/features/auth/pages/Login.test.tsx src/features/auth/api/loginSchema.test.ts --coverage
```

**LOC budget**: ~200 (production 120 + tests 80).

---

### §3.2 Task T2 — integrar POST /auth/login con credentials:'include' + error mapping

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done (apply 2026-09-15, commit 8b84b3e) |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~80 LOC delta) |
| **Order** | 2 (segunda de C1; corre DESPUÉS de T1 porque wirea `postLogin` en `onSubmit` de T1) |
| **Cluster** | C1 |
| **Pre-requisitos** | T1 merged; `apps/ui-kit/src/fetch/parkosFetch.ts` provee `ParkosHttpError` (F2.2) |
| **Acceptance gates** | G3 (fetch con credentials:'include' + Content-Type JSON), G5 (429 → `AccountLockedError(retryAfter)`) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- NEW: `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (~30 LOC — `postLogin` con fetch raw + `InvalidCredentialsError` + `AccountLockedError` + `TokenPair` interface).
- NEW: `apps/electron-sucursal/src/features/auth/api/loginApi.test.ts` (~50 LOC — vitest con `vi.spyOn(global, 'fetch')` mockeando 200/401/429/5xx; assert `credentials:'include'` + Content-Type JSON + custom error classes).
- MODIFY: `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (+5 LOC — `const pair = await postLogin(values.email, values.password); setTokens(pair.access_token, pair.refresh_token, pair.expires_in);`).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, ~50 LOC):
   - Test U1 (`loginApi.test.ts`): mock fetch 200 OK + body TokenPair → assert `postLogin('op@test.co', 'Pass1234word')` retorna `{access_token, refresh_token, token_type:'Bearer', expires_in}` parseado.
   - Test U2 (`loginApi.test.ts`): mock fetch 401 → assert `instanceof InvalidCredentialsError` + mensaje sin distinción email/password.
   - Test U3 (`loginApi.test.ts`): mock fetch 429 + `Retry-After: 600` header → assert `instanceof AccountLockedError` + `error.retryAfterSeconds === 600`.
   - Test U4 (`loginApi.test.ts`): mock fetch 500 → assert `instanceof ParkosHttpError` + `error.status === 500`.
   - Test U5 (`loginApi.test.ts`): spy fetch call args → assert `credentials: 'include'` + `Content-Type: application/json` + body JSON.stringify `{email, password}`.
   - Test U9 (`Login.test.tsx`): mock fetch 200 + `useAuth` retorna `{data:{user:{...}}, isAuthenticated:true, isLoading:false}` → assert `setTokens` spy llamado con `(access, refresh, 3600)`.
   - Test U10 (`Login.test.tsx`): mock fetch 401 + assert `<p role="alert" data-testid="login-error-invalid">` muestra `t('invalidCredentials')`.

2. **GREEN** (implementación mínima, ~30 LOC):
   - `loginApi.ts` (~30 LOC):
     - `interface TokenPair { access_token: string; refresh_token: string; token_type: 'Bearer'; expires_in: number }`.
     - `class InvalidCredentialsError extends Error { readonly name = 'InvalidCredentialsError' }`.
     - `class AccountLockedError extends Error { constructor(public readonly retryAfterSeconds: number) { super(...) } readonly name = 'AccountLockedError' }`.
     - `async function postLogin(email, password): Promise<TokenPair>` con `fetch('/api/v1/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, credentials:'include', body:JSON.stringify({email, password})})` + error mapping 401/429/5xx.
   - `Login.tsx` MODIFY (+5 LOC): en `onSubmit`, `try { const pair = await postLogin(...); setTokens(pair.access_token, pair.refresh_token, pair.expires_in); } catch (err) { if (err instanceof InvalidCredentialsError) setErrorState({kind:'invalid_credentials'}); else if (err instanceof AccountLockedError) setErrorState({kind:'lockout', retryAfterSeconds: err.retryAfterSeconds}); else setErrorState({kind:'network'}); }`.

3. **REFACTOR** (extract constants, JSDoc):
   - `LOGIN_PATH = '/api/v1/auth/login'` constante module-level.
   - JSDoc cross-ref DEC-F3.1-03/04/05/08 en cada función/clase exportada.
   - Helper `parseRetryAfter(headerValue)` extraído con validación `Number.isFinite`.

**Commit message**:

```
feat(auth): integrar POST /auth/login con credentials:'include' + error mapping 401/429
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm vitest run src/features/auth/api/loginApi.test.ts src/features/auth/pages/Login.test.tsx --coverage
```

**LOC budget**: ~80 (production 30 + tests 50).

---

### §3.3 Task T3 — Login redirige a `/` tras hidratar authStore desde /auth/me

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done (apply 2026-09-15, commit 70d9aa1) |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~50 LOC delta) |
| **Order** | 3 (tercera de C1; corre DESPUÉS de T2 porque `useEffect` redirect depende de `setTokens` de T2) |
| **Cluster** | C1 |
| **Pre-requisitos** | T2 merged; `useAuth()` SWR hook disponible en `@parkos/ui-kit/hooks` (F2.2) |
| **Acceptance gates** | G4 (`useAuth().data.user` hidrata antes de `navigate('/')`) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- MODIFY: `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (+10 LOC — `import { useEffect } from 'react'` + `const {isAuthenticated, isLoading, data} = useAuth()` + `useEffect([isAuthenticated, data?.user, isLoading, navigate], () => { if (isAuthenticated && data?.user && !isLoading) navigate('/', {replace:true}) })`).
- MODIFY: `apps/electron-sucursal/src/renderer/App.tsx` (+5 LOC — `import { Login } from '../features/auth/pages/Login'` + `<Route path="/login" element={<Login />} />`).
- MODIFY: `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (+30 LOC — tests U13 redirect NO dispara si `data.user === undefined` + U14 redirect SÍ dispara post `data.user` resuelto).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, +30 LOC):
   - Test U13 (`Login.test.tsx`): mock `useAuth` retorna `{isAuthenticated:true, isLoading:true, data:undefined}` → render → assert `mockNavigate` NOT called.
   - Test U14 (`Login.test.tsx`): mock `useAuth` retorna `{isAuthenticated:true, isLoading:false, data:{user:{uuid:'u1', email:'op@test.co'}}}` → render → assert `mockNavigate` called con `'/'` + `{replace:true}`.
   - Test U15 (`Login.test.tsx`): mock `useAuth` retorna `{isAuthenticated:false, data:undefined}` (NO setTokens previo) → render → assert `mockNavigate` NOT called.

2. **GREEN** (implementación mínima, +15 LOC):
   - `Login.tsx` (+10 LOC):
     - `import { useEffect } from 'react'`.
     - `import { useAuth } from '@parkos/ui-kit/hooks'`.
     - `import { useNavigate } from 'react-router-dom'`.
     - `const navigate = useNavigate()`.
     - `const { isAuthenticated, isLoading, data } = useAuth()`.
     - `useEffect(() => { if (isAuthenticated && data?.user && !isLoading) navigate('/', { replace: true }); }, [isAuthenticated, data?.user, isLoading, navigate])`.
   - `App.tsx` (+5 LOC):
     - `import { Login } from '../features/auth/pages/Login'`.
     - `<Route path="/login" element={<Login />} />` entre `<Route path="/" element={null} />` y `<Route path="*" element={...} />`.

3. **REFACTOR** (extract constants, JSDoc):
   - JSDoc cross-ref DEC-F3.1-07 en `useEffect` con explicación "hidratación transaccional sin flash".
   - Helper `shouldRedirect(isAuthenticated, isLoading, data)` extraído (testeable aislado).

**Commit message**:

```
feat(router): adicionar ruta /login con redirect a / post-hidratación useAuth()
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm tsc --noEmit -p tsconfig.renderer.json && pnpm vitest run src/features/auth/pages/Login.test.tsx --coverage
```

**LOC budget**: ~50 (production 20 + tests 30).

---

### §3.4 Task T4 — e2e login.spec.ts (3 casos + axe-core)

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done (apply 2026-09-15, commit 5fcfe66) |
| **Type** | test |
| **Atomicidad** | sí (1 commit, ~80 LOC delta tests only) |
| **Order** | 4 (última de C1; corre DESPUÉS de T1+T2+T3 mergeados) |
| **Cluster** | C1 |
| **Pre-requisitos** | T1 + T2 + T3 done; `apps/electron-sucursal/playwright.config.ts` auto-discovers `e2e/**/*.spec.ts` (F2.1) |
| **Acceptance gates** | G6 (3 e2e scenarios verde), G7 implícito (axe-core 0 violaciones WCAG 2.1 AA) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Sandbox F.6 caveat**: npm 11.16.0 en sandbox refuses `workspace:*` resolution. e2e G6 SKIPPED en este ambiente; CI matrix required. NO es project defect — precedent F2.1 + F2.2 + F2.3 verbatim.

**Files**:
- NEW: `apps/electron-sucursal/e2e/auth/login.spec.ts` (~80 LOC — 3 scenarios + axe-core).

**E2E scenarios** (per `plan.md:1295` + `design.md §13.2` verbatim):

- **E1 — login-ok-cookie**: operador tipea `email + password` válidos → submit → cookie `parkos_session` set (`page.context().cookies()` con `httpOnly: true` + `sameSite: 'Lax'`) → redirect a `/` → `useAuth().user.email === <test email>`.
- **E2 — refresh-transparente**: login OK primero → mock `/auth/me` para retornar 401 una vez → assert `useAuth` SWR dispara refresh-once (`parkosFetch` detecta 401 → refresh-once via Mutex) → redirect a `/login` (forward F3.3+ AuthGuard consumer).
- **E3 — logout**: login OK primero → `useAuthStore.clear()` via `window.bridge.authStore.delete('parkos.auth')` (test-only injection) → `/auth/me` retorna 404 → `useAuth()` limpia store + emite `parkos:auth:cleared` event → forward AuthGuard stub verifica redirect a `/login`.
- **A1 — axe-core WCAG 2.1 AA en /login**: `await page.goto('/login')` → `new AxeBuilder({page}).analyze()` con tags `wcag2a, wcag2aa, wcag21a, wcag21aa` → assert `results.violations` length === 0 (G7 REQ-OPS-112).

**Commit message**:

```
test(electron): adicionar 3 e2e login (cookie httpOnly + refresh transparente + logout)
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm playwright test e2e/auth/login.spec.ts
```

**LOC budget**: ~80 tests.

---

### §3.5 C1 commits ledger

| Hash TBD | Task | +LOC | -LOC | Files | Commit message |
|---|---|---|---|---|---|
| TBD-1 | T1 Login + LoginForm + Zod | +200 | -10 | 6 | `feat(auth): adicionar Login page con RHF+Zod (email/password) + LoginForm presentacional + 5 i18n validation keys` |
| TBD-2 | T2 postLogin + error mapping | +80 | -5 | 3 | `feat(auth): integrar POST /auth/login con credentials:'include' + error mapping 401/429` |
| TBD-3 | T3 redirect + /login route | +50 | -3 | 3 | `feat(router): adicionar ruta /login con redirect a / post-hidratación useAuth()` |
| TBD-4 | T4 e2e 3 scenarios | +80 | 0 | 1 | `test(electron): adicionar 3 e2e login (cookie httpOnly + refresh transparente + logout)` |
| **TOTAL C1** | — | **+410** | **-18** | **13** | — |

**Net LOC delta**: `+410 - 18 = +392 net LOC production + tests`.

---

## §4. Atomic commits ledger (consolidado)

| Hash TBD | Task | Cluster | Files | +LOC | -LOC | Commit message |
|---|---|---|---|---|---|---|
| TBD-1 | T1 Login + LoginForm | C1 | 6 | +200 | -10 | `feat(auth): adicionar Login page con RHF+Zod (email/password) + LoginForm presentacional + 5 i18n validation keys` |
| TBD-2 | T2 postLogin + error mapping | C1 | 3 | +80 | -5 | `feat(auth): integrar POST /auth/login con credentials:'include' + error mapping 401/429` |
| TBD-3 | T3 redirect + /login route | C1 | 3 | +50 | -3 | `feat(router): adicionar ruta /login con redirect a / post-hidratación useAuth()` |
| TBD-4 | T4 e2e 3 scenarios | C1 | 1 | +80 | 0 | `test(electron): adicionar 3 e2e login (cookie httpOnly + refresh transparente + logout)` |
| **TOTAL** | **4 atomic** | **1 cluster** | **13** | **+410** | **-18** | — |

**Net LOC delta**: `+410 - 18 = +392 net LOC production + tests`.

**Plan 190 LOC matches**: `~390 production + tests` ≈ `~410 (170 production + 10 i18n/configs + 20 JSDoc + 240 tests) - 18 deletions`.

---

## §5. Files inventory

Cross-ref `exploration.md §18` + `design.md §B.1` + `proposal.md §2.1` verbatim.

### §5.1 NEW (7 archivos production + tests)

| Path | Task | LOC target | Descripción |
|---|---|---|---|
| `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` | T1 | 60 | Presentational puro (shadcn Form + FormField + FormMessage + role=alert). |
| `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` | T1 | 30 | Render presentacional + axe-core 0 violaciones. |
| `apps/electron-sucursal/src/features/auth/api/loginSchema.ts` | T1 | 10 | Zod `loginSchema` + `LoginInput` type. |
| `apps/electron-sucursal/src/features/auth/api/loginApi.ts` | T2 | 30 | `postLogin` (fetch raw) + `TokenPair` + `InvalidCredentialsError` + `AccountLockedError`. |
| `apps/electron-sucursal/src/features/auth/api/loginApi.test.ts` | T2 | 50 | vi.spyOn(global, 'fetch') mocks 200/401/429/5xx + assert credentials:'include'. |
| `apps/electron-sucursal/src/features/auth/pages/Login.tsx` | T1+T2+T3 | 75 | Container RHF + Zod + postLogin + useAuth + useNavigate + useEffect redirect. |
| `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` | T1+T2+T3 | 80 | 6 scenarios: U9 submit OK, U10 401, U11/U12 Zod invalid, U13 redirect wait, U14 redirect fire. |
| `apps/electron-sucursal/e2e/auth/login.spec.ts` | T4 | 80 | 3 scenarios e2e + axe-core. |
| **TOTAL NEW** | T1..T4 | **~415 LOC** | — |

### §5.2 MODIFY (3 archivos)

| Path | Task | Delta LOC | Descripción |
|---|---|---|---|
| `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` | T1 | +5 keys | Sub-objeto `validation.{required, email.invalid, password.{minLength, required}}`. |
| `apps/electron-sucursal/src/renderer/App.tsx` | T3 | +5 LOC | `<Route path="/login" element={<Login />} />`. |
| `apps/electron-sucursal/electron/` (sin cambios — F3.1 NO toca main process) | — | 0 | DEC-F3.1-04 HTTP directo, NO IPC. |
| **TOTAL MODIFY** | T1+T3 | **~10 LOC delta** | — |

### §5.3 READ ONLY (16 archivos — anchors)

| Path | Precedent | Razón NO F3.1 touch |
|---|---|---|
| `apps/electron-sucursal/electron/main.ts` | F2.3 | DEC-F3.1-04 login HTTP no IPC; main process intacto. |
| `apps/electron-sucursal/electron/preload.ts` | F2.2 | F3.1 NO expone nuevos métodos bridge. |
| `apps/electron-sucursal/electron/bridge.d.ts` | F2.2+F2.3 | F3.1 NO agrega tipos bridge. |
| `apps/ui-kit/src/fetch/parkosFetch.ts` | F2.2 | DEC-F3.1-05 raw fetch para login (NO consume parkosFetch). |
| `apps/ui-kit/src/store/authStore.ts` | F2.2 | `setTokens` ya existe atómico. |
| `apps/ui-kit/src/hooks/useAuth.ts` | F2.2 | SWR ya hidrata desde /auth/me con refresh 5min. |
| `apps/ui-kit/package.json` | F2.2 | zustand ya en deps. |
| `apps/electron-sucursal/src/renderer/components/ui/{form,input,button}.tsx` | F2.1 | F3.1 reusa shadcn primitives sin modificar. |
| `apps/electron-sucursal/src/renderer/i18n/index.ts` | F2.1 | auth namespace ya registrado. |
| `apps/electron-sucursal/src/renderer/i18n/locales/{common,operacion,caja,facturacion,sync,errors}.json` | F2.1 | F3.1 NO agrega namespaces. |
| `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` | F2.3 | StatusBar visible durante login (sin modificación). |
| `apps/electron-sucursal/src/renderer/main.tsx` | F2.1 | BrowserRouter ya wrappea. |
| `apps/electron-sucursal/e2e/{scaffold,auth/parkos-fetch,auth/bridge,a11y/wcag-2.1-aa,lifecycle,kiosko}.spec.ts` | F2.1+F2.2+F2.3 | F3.1 NO toca los e2e existentes. |
| `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py` | HU-F1.2 shipped | F3.1 NO modifica backend. |
| `backend/packages/parkos_core/src/parkos_core/schemas/auth.py` | HU-F1.2 shipped | F3.1 consume LoginRequest + TokenPair + AuthMeResponse. |
| `openspec/specs/operations/spec.md` | canonical | F3.1 AGREGA 7 new REQ-OPS-106..112 (post-archive merge). |

### §5.4 Total de impacto

- **NEW**: 8 archivos de producción + tests (~415 LOC).
- **MODIFY**: 2 archivos de producción + i18n (~10 LOC delta + 5 keys).
- **READ ONLY**: 16 archivos.
- **TOTAL IMPACT**: 26 archivos de 415 LOC nuevos + 10 LOC delta.

---

## §6. Acceptance gates mapping

Cross-ref `proposal.md §11` + `design.md §11` + `exploration.md §12` + `spec.md §5` verbatim.

| Gate | Task | Mechanism | File | Verification command |
|---|---|---|---|---|
| **G1** | T1 | vitest unit (RHF+Zod validation inline) | `LoginForm.test.tsx` + `Login.test.tsx` | `pnpm vitest run src/features/auth/components/LoginForm.test.tsx src/features/auth/pages/Login.test.tsx --coverage` |
| **G2** | T1 | vitest unit (mock 401 → `t('invalidCredentials')`) | `Login.test.tsx` U10 | idem G1 |
| **G3** | T2 | vitest unit (assert request `credentials:'include'` + Content-Type JSON) | `loginApi.test.ts` U5 | `pnpm vitest run src/features/auth/api/loginApi.test.ts --coverage` |
| **G4** | T2 + T3 | vitest unit (mock 200 + assert setTokens + useEffect fires) | `Login.test.tsx` U9 + U14 | idem G1 |
| **G5** | T2 | vitest unit (mock 429 + Retry-After) | `loginApi.test.ts` U3 | idem G3 |
| **G6** | T4 | playwright e2e (`_electron.launch` 3 scenarios) | `login.spec.ts` | `pnpm playwright test e2e/auth/login.spec.ts` |
| **G7 (implícito)** | T1 + T4 | axe-core WCAG 2.1 AA 0 violaciones | `LoginForm.test.tsx` U8 + `login.spec.ts` A1 | `pnpm vitest run src/features/auth/components/LoginForm.test.tsx && pnpm playwright test e2e/auth/login.spec.ts` |

**Estado pre-flight target**: 0/7 PASS al inicio; **7/7 PASS** post-implementación en local dev (Windows native npm 11.16+) o CI matrix con image compatible.

**Sandbox F.6 caveat**: G6 SKIPPED en sandbox F.6 (npm 11.16.0 refuses workspace:*). G1, G2, G3, G4, G5, G7 (axe-core unit) pueden ejecutar con mocks (sin necesidad de workspace resolution post-install). Documentado en §10.

---

## §7. Verification contract (cross-ref `sdd-verify`)

`sdd-verify` debe validar los siguientes criterios antes de emitir PASS:

1. **4 atomic commits** en `feat/fase-2-electron-scaffold` con:
   - Author: `Parkos Dev <dev@parkos.local>` (verificado via `git log --format='%an <%ae>'`).
   - **SIN** `Co-authored-by` trailer (verificado via `git log --format='%(trailers)' --grep='Co-authored-by'` retorna vacío).
   - **SIN** AI trailers (no `Signed-off-by` automático, no `[AI]`, no `Generated by`).
   - Mensajes verbatim de §4 commits ledger.

2. **7/7 acceptance gates** evaluados:
   - G1, G2, G3, G4, G5, G7 (unit + axe-core) ejecutan localmente.
   - G6 (e2e) ejecuta solo en CI matrix (sandbox F.6 SKIPPED-env-blocked documentado).

3. **Coverage thresholds** (cross-ref design §11.5 + tsconfig `coverage.thresholds`):
   - `src/features/auth/pages/Login.tsx` ≥80% lines, ≥80% functions, ≥75% branches.
   - `src/features/auth/components/LoginForm.tsx` ≥80% lines, ≥80% functions, ≥75% branches.
   - `src/features/auth/api/loginApi.ts` ≥80% lines, ≥80% functions, ≥75% branches.
   - Verificado via `vitest --coverage` en CI matrix.

4. **TypeScript strict**:
   - `pnpm tsc --noEmit -p tsconfig.renderer.json` limpio en archivos nuevos.
   - `pnpm tsc --noEmit -p tsconfig.main.json` limpio (F3.1 NO toca main, pero verificable).
   - **CERO** `any` introducido en código nuevo.

5. **Unit tests verde**:
   - `pnpm vitest --run` en archivos nuevos (`LoginForm.test.tsx`, `Login.test.tsx`, `loginApi.test.ts`) verde.

6. **Canonical `openspec/specs/operations/spec.md` DELTA mergeado**:
   - Post-archive, las 7 new REQ-OPS-106..112 están mergeadas al spec canónico (byte count incrementado).
   - Numeración monotónica verificada: REQ-OPS-105 vigente pre-archive → REQ-OPS-106..112 nuevos.

7. **i18n keys nuevas**:
   - `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` delta con 5 keys sub-objeto `validation` (snapshot test estable).

8. **Defense in depth XR6 (5 capas)** preservado + REQ-OPS-106..112:
   - Layer 1 auth: HU-F1.2 backend bcrypt + JWT + cookie httpOnly SameSite=Lax.
   - Layer 2 engineering: TS strict + noUncheckedIndexedAccess.
   - Layer 3 a11y: axe-core WCAG 2.1 AA + FormField aria-invalid + FormMessage role=alert (REQ-OPS-112).
   - Layer 4 contract: Zod validation form (DEC-F3.1-06) + backend Pydantic + 7 new REQ-OPS-106..112 (DEC-F3.1-11).
   - Layer 5 retry-budget: parkosFetch retry 5xx + 401 refresh-once (F2.2 — F3.1 NO custom retry en login).

---

## §8. Sandbox F.6 + npm 11.16.0 caveat

Cross-ref `exploration.md §13` + `design.md §15.5` + precedent F2.1 + F2.2 + F2.3 archive reports.

**Documentación obligatoria**:

- `npm 11.16.0` en sandbox F.6 refuses `workspace:*` resolution (`apps/ui-kit` consume `apps/electron-sucursal` etc.). Esto bloquea `pnpm/npm install` con workspaces.
- e2e G6 (playwright `_electron.launch`) SKIPPED en este ambiente — `pnpm install` falla antes de poder ejecutar tests.
- **NO es project defect** — precedent verbatim F2.1 + F2.2 + F2.3 archive reports documentan misma limitation.
- e2e verdes en local dev (Windows native npm 11.16+) o CI con image compatible (ubuntu-latest, macos-latest).
- Unit tests G1, G2, G3, G4, G5, G7 (axe-core unit) ejecutan con mocks (no requieren workspace resolution post-install) — estos sí corren localmente.

**Acciones en verify-report**:

- `verify-report.md` documenta D-env deviation: "e2e G6 SKIPPED en sandbox F.6 — CI matrix required para validar".
- `verify-report.md` lista los 6 unit gates PASS (G1, G2, G3, G4, G5, G7) y el 1 e2e gate DEFERRED (G6) a CI.
- Status final del verify: `partial — CI matrix required para completar G6` (NO `fail`).

---

## §9. Forward hooks (a Fase 3+)

Cross-ref `proposal.md §14` + `design.md §14` + `exploration.md §15`.

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.2** (lockout visible + refresh pre-flight) | `AccountLockedError(retryAfterSeconds)` de F3.1 → F3.2 `useCountdown` hook | F3.2 wraps Login.tsx onSubmit con disable form durante countdown + `<Countdown seconds={retryAfterSeconds} />` + 50min auto-refresh check pre-flight. |
| **HU-F3.3** (abrir/cerrar turno) | `useAuth().user.sucursal` + `permisos[]` hidratados post-F3.1 | F3.3 `AbrirTurno` lee `user.sucursal.uuid` y filtra `permisos.includes('caja.apertura')` antes de POST `/caja-sesion/sesiones`. |
| **HU-F3.x** (logout button UI) | `useAuthStore.clear()` ya implementado en F2.2 + `parkos:auth:cleared` window event | F3.x `<LogoutButton onClick={() => useAuthStore.getState().clear() + navigate('/login')} />`. |
| **HU-F3.x** (AuthGuard component) | `parkos:auth:cleared` window event | F3.x `<AuthGuard>` escucha evento → `navigate('/login?next=...')`. F3.1 Login page NO necesita AuthGuard (es el entry point). |
| **HU-F4.x** (catálogos + ocupación) | `useAuth()` + parkosFetch | F4.x lee `user.sucursal.uuid` para scoped queries a `/productos/*`. |
| **HU-F5.x+** (impresión térmica) | `useAuth().permisos` filter | F5.x verifica `permisos.includes('facturacion.emitir')` antes de imprimir ticket. |
| **HU-F11.x** (sync UI topbar) | useAuth (no directo) | F11.x muestra `user.email` en topbar post-login. |
| **PR7 backend** (refresh-token rotation) | authStore + refresh logic (no F3.1) | Detección de reuse `jti` claim (F2.2 DEC-FETCH-03 cubre sin rotation; rotación es PR7+). |

---

## §10. Implementation strategy (TDD strict per task)

Cross-ref `exploration.md §10` + `design.md §11` + `proposal.md §13`.

### §10.1 Reglas globales

- **TDD strict**: cada test escrito ANTES de la implementación. Tests rojos primero (RED), luego código que los hace verde (GREEN), luego refactor (REFACTOR).
- **Cobertura >80% exigida** en `Login.tsx` + `LoginForm.tsx` + `loginApi.ts` (vitest --coverage threshold per tsconfig).
- **Cobertura snapshot** en i18n `auth.json` con 5 nuevas validation keys (no regression).
- **Conventional commits** neutrales español: `feat(auth)`, `feat(router)`, `test(electron)`.
- **NO Co-authored-by**, **NO AI trailers** (verificación §7 #1).
- **CERO `any`** introducido en código nuevo.

### §10.2 Pre-flight gates (per task)

| Task | RED (tests rojos primero) | GREEN (implementación mínima) | REFACTOR (extract + JSDoc) | Commit |
|---|---|---|---|---|
| **T1** | `LoginForm.test.tsx` U6/U7/U8 + `Login.test.tsx` U11/U12 + snapshot `auth.json` | `loginSchema.ts` + `LoginForm.tsx` + `Login.tsx` base + `auth.json` delta | Constants testid + JSDoc DEC-F3.1-02/06 + helper `getErrorMessage` | `feat(auth): adicionar Login page con RHF+Zod...` |
| **T2** | `loginApi.test.ts` U1/U2/U3/U4/U5 + `Login.test.tsx` U9/U10 | `loginApi.ts` + `Login.tsx` MODIFY (+5 LOC) | `LOGIN_PATH` constant + JSDoc DEC-F3.1-03/04/05/08 + helper `parseRetryAfter` | `feat(auth): integrar POST /auth/login con credentials:'include'...` |
| **T3** | `Login.test.tsx` U13/U14/U15 | `Login.tsx` MODIFY (+10 LOC useEffect) + `App.tsx` MODIFY (+5 LOC) | JSDoc DEC-F3.1-07 + helper `shouldRedirect` | `feat(router): adicionar ruta /login con redirect a /...` |
| **T4** | e2e stubs E1/E2/E3 + A1 (axe-core) | `login.spec.ts` con 3 scenarios + axe-core | Doc comments cross-ref DEC-F3.1-10 | `test(electron): adicionar 3 e2e login...` |

### §10.3 Order strictness

- **No-paralelización**: T1 → T2 → T3 → T4 mandatory. Cada task depende de la anterior (cross-ref §2.3 justificación).
- **Single cluster C1**: los 4 tasks son una unidad end-to-end (login flow completo). No se pueden dividir en features independientes.
- **No reordering**: si T2 se intenta ejecutar antes de T1, los tests de `loginApi.test.ts` U9/U10 (`Login.test.tsx`) fallan al no existir `Login.tsx` con `postLogin` import.
- **No rollback parcial**: si T3 falla, NO se commitea T2 standalone — se revierte T2 también (atomic cluster C1).

---

## §11. DoD checklist

Cross-ref `proposal.md §16.4` + `design.md §11.5` + `exploration.md §13`.

- [ ] **4 atomic commits T1..T4** con author `Parkos Dev <dev@parkos.local>` (verificado via `git log`).
- [ ] **NO Co-authored-by, NO AI trailers** en los 4 commits (verificado via `git log --format='%(trailers)'`).
- [ ] **Conventional commits** neutrales español: `feat(auth)` × 2 + `feat(router)` × 1 + `test(electron)` × 1.
- [ ] **`pnpm vitest --run` verde** en archivos nuevos: `Login.test.tsx` + `LoginForm.test.tsx` + `loginApi.test.ts`.
- [ ] **`pnpm tsc --noEmit -p tsconfig.renderer.json` clean** en archivos nuevos (zero TS errors).
- [ ] **axe-core 0 violaciones** en `LoginForm` (G7 REQ-OPS-112) — vitest `vitest-axe` matcher.
- [ ] **e2e SKIPPED-env** documentado (G6 deviation D-env en `verify-report.md` — sandbox F.6 npm 11.16.0 refuses workspace:*).
- [ ] **No regresiones en suite e2e Fase 2** (F2.1 + F2.2 + F2.3 e2e siguen verdes post-merge F3.1).
- [ ] **Coverage thresholds** cumplidos: `Login.tsx` ≥80%, `LoginForm.tsx` ≥80%, `loginApi.ts` ≥80% (vitest --coverage).
- [ ] **CERO `any`** introducido en código nuevo (TS strict + lint).
- [ ] **Working tree clean post-apply** (`git status --short` retorna vacío post-archive).
- [ ] **`auth.json` snapshot estable** con 5 nuevas validation keys (snapshot test verde).
- [ ] **`pending.md` §1 row F3.1 → ✅ cerrado** (archive phase post-verify).
- [ ] **`openspec/specs/operations/spec.md` REQ-OPS-106..112 mergeados** (post-archive byte count incrementado).

---

## §12. Risks & mitigations (per task)

Cross-ref `exploration.md §7` R1..R8 + `design.md §10` verbatim.

| # | Risk | Severity | Task | Mitigación |
|---|---|---|---|---|
| **R1** | **CSRF attack en /auth/login** — atacante hace que el operador submita login via cross-site form | MEDIUM | T2 | DEC-F3.1-03: `credentials:'include'` + `SameSite=Lax` en cookie bloquea cross-site POST. Backend CORS verifica `Origin` header (no F3.1 scope). |
| **R2** | **Cookie theft via XSS** — atacante inyecta script que lee `document.cookie` | LOW (mitigado) | T2 | DEC-F3.1-03: `HttpOnly` flag en `parkos_session` impide lectura via JS. CSP estricto en renderer (F2.1 baseline). |
| **R3** | **Cookie no persiste en reload** — operador refresca `/login` y la cookie se pierde | LOW (NO debería pasar) | T2 + T3 | Browser persiste cookies httponly hasta `Max-Age` (3600s). `useAuth()` SWR re-fetcha `/auth/me` con cookie auto-enviada → re-hidrata store. |
| **R4** | **Race condition entre setTokens y useAuth()** — SWR dispara `/auth/me` antes de `setTokens` complete | LOW | T2 + T3 | DEC-F3.1-07: el `useEffect` espera `data?.user` (no solo `isAuthenticated`). Zustand setState es síncrono, sin race. |
| **R5** | **Login form expuesto a timing attacks** — atacante mide latencia para inferir email existe | LOW | T1 (NO acción directa) | Backend usa `bcrypt.checkpw` (~250ms) dominantly-costly vs DB lookup (~10ms). Diferencia enmascarada por bcrypt cost. Frontend mensaje único `t('invalidCredentials')` tampoco revela. |
| **R6** | **Zod schema drift frontend/backend** — `password: min(8)` vs backend `min_length:8` mismatch | LOW | T1 | Plan.md:1291 verbatim `z.string().min(8)`. Backend `StringConstraints(min_length:8, max_length:128)`. Match. Si backend cambia, frontend NO rompe (devuelve 422) pero UX degrada. |
| **R7** | **password en memoria via form state** — RHF storea password en formState | LOW | T1 + T3 | RHF mantiene form state en memoria del componente. Cuando `<LoginPage>` unmounts (post-redirect a `/`), React garbage-collects `formState`. NO persiste a electron-store. Aceptable para kiosko desatendido. |
| **R8** | **e2e sandbox F.6 SKIP** — playwright `_electron` no arranca en sandbox | MEDIUM (env) | T4 | F2.2 archive precedent: SKIPPED en npm 11.16.0. F3.1 e2e va a SKIP misma manera. Documentado como D-env en `verify-report.md`. Unit tests cubren camino crítico. |

**Riesgos identificados y cerrados**: 8/8 con mitigación explícita. 0 KNOWN-MISSING.

---

## §13. CHANGELOG

- (2026-09-15) **F3.1 tasks phase complete** — 4 atomic tasks T1..T4 across 1 cluster C1 (end-to-end, orden interno T1 → T2 → T3 → T4 mandatory). ~430 LOC total (production 190 + tests 240). 7 acceptance gates G1..G6 + G7 axe-core WCAG 2.1 AA mapeados a unit + e2e + a11y mechanisms. 11 DEC-F3.1-NN ratificadas (cross-ref proposal §5 + exploration §6 + design §5). 7 new REQ-OPS-106..112 user-facing (DEC-F3.1-11 — DELTA stub precedent F1.15 verbatim). Sandbox F.6 caveat documentado (e2e G6 SKIPPED local, CI matrix required). Plan 190 LOC production matches verbatim. Ready for `sdd-apply`.

---

**End of tasks — HU-F3.1.**