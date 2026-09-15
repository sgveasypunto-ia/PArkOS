/**
 * parkosFetch — re-export from `@parkos/ui-kit/fetch` (F2.2 — DEC-FETCH-01).
 *
 * F2.1 shipped a local wrapper here (~66 LOC) that injected Bearer + X-Sucursal-Context.
 * F2.2 moves the canonical implementation into `@parkos/ui-kit` so the same
 * wrapper powers web_admin (here) and `electron-sucursal` (renderer).
 *
 * Backwards-compatible surface: `import { parkosFetch } from '@/lib/fetch'`
 * continues to resolve to the same name and signature; consumers like
 * `apps/web_admin/src/pages/Dashboard.tsx` keep working unchanged.
 *
 * Capabilities ADDED in F2.2 (transparent to callers):
 *   - retry 5xx + 408 with backoff 300/600/1200 ms
 *   - 401 refresh-once via Mutex singleton (DEC-FETCH-03)
 *   - Idempotency-Key SHA-256 on mutaciones (DEC-FETCH-04)
 *   - Zod validation boundary via `parkosFetch<T>(url, init, schema)`
 *   - AbortController timeout via `init.timeoutMs`
 *
 * Legacy helpers `setAuthToken` / `getAuthToken` (F2.1 localStorage-based)
 * are removed; the new auth surface lives in `@parkos/ui-kit/store`
 * (authStore Zustand) and is consumed in F3.1+ via the `useAuth()` hook.
 */
export {
  parkosFetch,
  parkosFetchRaw,
  ParkosHttpError,
  type ParkosFetchInit,
} from '@parkos/ui-kit/fetch';
