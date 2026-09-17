/**
 * Tarifas store IPC service (HU-F4.2 — T1.3, design.md §Architecture).
 *
 * Pure sync helpers over the `StoreLike` interface (`kiosko.ts`) that the
 * main-process IPC handlers in `main.ts` invoke. Mirrors the precedent set
 * by `tryUnlockKiosko`: the IPC handler is a thin shell, the persistence
 * logic lives here so it can be unit-tested without spinning up Electron.
 *
 * The values stored under the `tarifas-store:*` namespace are JSON-encoded
 * strings (the renderer serializes the full snapshot on `set`). On `get`,
 * non-string values are JSON-stringified defensively so the renderer's
 * `JSON.parse` always succeeds; `null` and `undefined` map to `null` (the
 * renderer's `useTarifasVigentes` treats that as "no cache yet").
 *
 * Defense in depth XR6 layer 4 — 404 semantics (DEC-F4.2-04):
 * the renderer expects `{items:[], next_cursor:null}` when the API returns
 * 404 (sucursal sin tarifas configuradas). That path does NOT touch this
 * module — `tarifas-store:get` is for the electron-store cache only.
 */
import type { StoreLike } from './kiosko';

/**
 * Read a value from the tarifas electron-store namespace.
 *
 * Returns `null` for missing keys (the common case during cold start).
 * Coerces non-string stored values to JSON so the renderer can `JSON.parse`
 * them uniformly.
 */
export function readTarifasValue(store: StoreLike, key: string): string | null {
  const raw = store.get(key);
  if (raw == null) return null;
  if (typeof raw === 'string') return raw;
  return JSON.stringify(raw);
}

/**
 * Persist a JSON-serializable value under the given tarifas-store key.
 * The renderer is expected to pass an already-serialized JSON string so
 * the round-trip preserves the shape verbatim; this helper does NOT
 * re-serialize (callers wrap with `JSON.stringify`).
 */
export function writeTarifasValue(store: StoreLike, key: string, value: string): void {
  store.set(key, value);
}

/**
 * Remove a key from the tarifas electron-store namespace. Subsequent
 * `readTarifasValue` calls return `null`. No-op for missing keys.
 */
export function removeTarifasValue(store: StoreLike, key: string): void {
  // electron-store semantics: deleting a missing key is a no-op.
  store.set(key, undefined);
}
