/**
 * authStore — Zustand store for JWT tokens with persist middleware
 * against electron-store (via the `bridge.authStore` IPC channel
 * exposed in T3 by preload.ts).
 *
 * Design invariants (DEC-FETCH-06):
 *   - `accessToken === null` ↔ `refreshToken === null` ↔ `expiresAt === null`
 *     (atomic clear / atomic setTokens).
 *   - `expiresAt` is derived in `setTokens` from `Date.now() + expiresIn * 1000`
 *     and serialized as ISO 8601 UTC; callers never persist the raw `expiresIn`.
 *   - `partialize` whitelist: ONLY `{ accessToken, refreshToken, expiresAt }`
 *     cross the IPC seam into electron-store. Functions and derived data
 *     stay in memory.
 *
 * Refresh-once Mutex (DEC-FETCH-03):
 *   `refreshAccessToken()` is module-level; the first 401 caller starts
 *   the request and subsequent concurrent 401 callers await the SAME
 *   promise. After the request settles (success or failure) the slot
 *   is cleared so the NEXT 401 starts a fresh refresh.
 *
 * NOTE on the `parkos:auth:cleared` event:
 *   parkosFetch fires this window event when refresh fails so the SPA
 *   router can redirect to /login. authStore.clear() is the synchronous
 *   half of that contract.
 */
import { create } from 'zustand';
import {
  createJSONStorage,
  persist,
  type StateStorage,
} from 'zustand/middleware';

// ─── electron-store adapter (via preload IPC bridge) ────────────────
// Production: real `window.bridge.authStore.{get,set,delete}` from T3.
// Tests: stub the global before importing this module (see authStore.test.ts).
const electronStore: StateStorage = {
  getItem: async (key: string): Promise<string | null> => {
    const bridge = (globalThis as { window?: { bridge?: { authStore?: { get: (k: string) => Promise<string | null> } } } }).window?.bridge;
    if (!bridge?.authStore) return null;
    const value = await bridge.authStore.get(key);
    return value ?? null;
  },
  setItem: async (key: string, value: string): Promise<void> => {
    const bridge = (globalThis as { window?: { bridge?: { authStore?: { set: (k: string, v: string) => Promise<void> } } } }).window?.bridge;
    if (!bridge?.authStore) return;
    await bridge.authStore.set(key, value);
  },
  removeItem: async (key: string): Promise<void> => {
    const bridge = (globalThis as { window?: { bridge?: { authStore?: { delete: (k: string) => Promise<void> } } } }).window?.bridge;
    if (!bridge?.authStore) return;
    await bridge.authStore.delete(key);
  },
};

// ─── Types ──────────────────────────────────────────────────────────
export interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: string | null;
  setTokens: (access: string, refresh: string, expiresIn: number) => void;
  clear: () => void;
}

interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

// ─── Store ──────────────────────────────────────────────────────────
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
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        expiresAt: state.expiresAt,
      }),
      version: 1,
    },
  ),
);

// ─── Mutex singleton refresh (DEC-FETCH-03) ─────────────────────────
// Module-level so the singleton survives React re-renders. N concurrent
// 401 callers share ONE POST /auth/refresh; the rest await the same
// promise and retry with the resulting access_token.
let refreshPromise: Promise<string | null> | null = null;

const REFRESH_PATH = '/api/v1/auth/refresh';

export async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const { refreshToken } = useAuthStore.getState();
      if (!refreshToken) return null;
      const res = await fetch(REFRESH_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return null;
      const pair = (await res.json()) as TokenPair;
      useAuthStore
        .getState()
        .setTokens(pair.access_token, pair.refresh_token, pair.expires_in);
      return pair.access_token;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}
