/**
 * `resolveRequestUrl` — file://-origin rewrite for root-relative API paths.
 *
 * Every caller (sesionActivaApi, loginApi, salidaApi, etc.) builds root-
 * relative paths like `/api/v1/...` - correct for both web_admin (served
 * over https, path resolves against that origin) and electron-sucursal's
 * Vite DEV server (`http://localhost:5173`, proxies `/api` to api-sucursal
 * per vite.config.ts). Neither assumption holds for the PACKAGED electron-
 * sucursal app: `electron/main.ts`'s production branch loads the renderer
 * via `loadFile` (a `file://` URL - see vite.config.ts's `base: './'` fix
 * for the sibling bug this uncovered), and a root-relative `fetch('/api/...')`
 * against a `file://` document resolves to `file:///api/...`, not an HTTP
 * request to api-sucursal at all.
 *
 * Kept in its own leaf module (no other local imports) so both
 * `parkosFetch.ts` and `authStore.ts` (which `parkosFetch.ts` itself
 * imports) can depend on it without a circular import.
 *
 * `api-sucursal` binds to loopback (DEC-INST-01, HU-F24.1) but the PORT is
 * an installer-time choice (port reconciliation, DEC-INST-03) - a bare
 * hardcoded default here would only ever match the default port, baked
 * into the renderer bundle at BUILD time with no way to override it after
 * an install picks a different one. `window.bridge.config.getApiOrigin()`
 * (electron/preload.ts, backed by `PARKOS_API_ORIGIN` read in the main
 * process - main.ts never exposes raw env vars to the sandboxed renderer)
 * resolves the REAL configured origin at runtime; this only rewrites
 * root-relative paths, and only when the document itself was loaded via
 * `file:` (never true for web_admin, which is never file://-served, and
 * never true in tests/dev where `window.bridge` also doesn't exist), so
 * web_admin's behavior is unaffected either way.
 *
 * Resolved once, asynchronously, at module load - `resolveRequestUrl` must
 * stay synchronous (parkosFetch.ts calls it inline right before `fetch`),
 * so the very first request(s) during app boot may still see the default
 * for the brief window before the bridge call settles. Same tradeoff the
 * app already accepts for `apiStatus` polling.
 */
const ELECTRON_PACKAGED_API_BASE_DEFAULT = 'http://127.0.0.1:8000';
let resolvedApiBase = ELECTRON_PACKAGED_API_BASE_DEFAULT;

interface MinimalConfigBridge {
  config?: { getApiOrigin?: () => Promise<string> };
}

if (typeof window !== 'undefined') {
  const bridge = (window as unknown as { bridge?: MinimalConfigBridge }).bridge;
  bridge?.config?.getApiOrigin?.()
    .then((origin) => {
      if (typeof origin === 'string' && origin.length > 0) {
        resolvedApiBase = origin;
      }
    })
    .catch(() => {
      /* keep default - web_admin/tests/dev never have window.bridge anyway */
    });
}

export function resolveRequestUrl(input: RequestInfo | URL): RequestInfo | URL {
  if (
    typeof input === 'string' &&
    input.startsWith('/') &&
    typeof window !== 'undefined' &&
    // Optional chaining on `location` itself, not just `window` - a test
    // double or stub can replace `window` wholesale without a real
    // `location` (confirmed: authStore.test.ts's `stubBridge()` does
    // exactly this via `vi.stubGlobal('window', {...})`), which would
    // otherwise throw here and get silently swallowed by callers' try/catch
    // (e.g. refreshAccessToken's `catch { return null }`) - not a crash,
    // but a request that silently never happens.
    window.location?.protocol === 'file:'
  ) {
    return resolvedApiBase + input;
  }
  return input;
}
