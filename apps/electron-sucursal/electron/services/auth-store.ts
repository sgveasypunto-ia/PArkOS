/**
 * Auth store IPC service (pairing credentials).
 *
 * Same shape as `tarifas-store.ts`: pure sync helpers over the `StoreLike`
 * interface (`kiosko.ts`) that the main-process IPC handlers in `main.ts`
 * invoke. The IPC handler is a thin shell; the persistence logic lives here
 * so it is unit-testable without spinning up Electron.
 *
 * Why this module exists — the preload has always exposed
 * `window.bridge.authStore` and `PairingWizard.tsx` depends on it:
 *
 *   await window.bridge.authStore.set('parkos.sync_jwt', resp.sync_jwt);
 *
 * but `main.ts` only ever registered the `tarifas-store:*` namespace. Every
 * `auth-store:*` invoke therefore rejected with
 * "No handler registered for 'auth-store:get'" and the pairing sync JWT was
 * silently dropped on the floor — the branch paired against the cloud but
 * had no credential to authenticate its own pushes with.
 *
 * The two namespaces are distinct: `tarifas-store:*` caches the tarifas
 * snapshot for offline reads, `auth-store:*` holds the long-lived
 * branch-to-cloud credential. They share one `StoreLike` instance, so
 * separation is by key name — callers must use distinct prefixes
 * (`parkos.sync_jwt` for auth, the tarifas cache keys for their own).
 */
import type { StoreLike } from './kiosko';

/**
 * Read a value from the auth electron-store namespace.
 *
 * Returns `null` for missing keys (expected on cold start, before the
 * branch has been paired). Non-string stored values are JSON-stringified
 * defensively so the renderer's `JSON.parse` always succeeds.
 */
export function readAuthValue(store: StoreLike, key: string): string | null {
  const raw = store.get(key);
  if (raw == null) return null;
  if (typeof raw === 'string') return raw;
  return JSON.stringify(raw);
}

/**
 * Persist a value under the given auth-store key.
 *
 * The renderer passes an already-serialized string (the `sync_jwt` verbatim);
 * this helper does NOT re-serialize, so the round-trip preserves the token
 * byte-for-byte. A JWT must never be re-encoded — any whitespace or
 * escaping change makes it unparseable by the cloud verifier.
 */
export function writeAuthValue(store: StoreLike, key: string, value: string): void {
  store.set(key, value);
}

/**
 * Remove a key from the auth electron-store namespace. Subsequent
 * `readAuthValue` calls return `null`, so the branch falls back to
 * "unpaired" state. No-op for missing keys (electron-store semantics).
 */
export function removeAuthValue(store: StoreLike, key: string): void {
  // electron-store v8 rejects `set(key, undefined)` with
  // "Use `delete()` to clear values" — removal must go through `delete`.
  store.delete(key);
}
