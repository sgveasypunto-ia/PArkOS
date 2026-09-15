import { create } from 'zustand';

/**
 * authStore — minimal stub for T1 (parkosFetch consumer).
 *
 * Full implementation (with `persist` middleware against electron-store)
 * arrives in T4 (C2 — State management cluster). T1 only needs the
 * `accessToken` getter that `parkosFetch.buildInit()` reads to inject
 * the `Authorization: Bearer` header.
 *
 * Test seam: tests can call `useAuthStore.setState({ accessToken: 'xxx' })`
 * to drive the Bearer-header assertion. T4 will retain this seam and
 * add a Mutex refresh helper + partialize whitelist.
 */

export interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: string | null;
  setTokens: (access: string, refresh: string, expiresIn: number) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()((set) => ({
  accessToken: null,
  refreshToken: null,
  expiresAt: null,
  setTokens: (access, refresh, _expiresIn) => {
    // T4 will derive the ISO `expiresAt` from `Date.now() + expiresIn * 1000`.
    void _expiresIn;
    set({ accessToken: access, refreshToken: refresh, expiresAt: null });
  },
  clear: () => set({ accessToken: null, refreshToken: null, expiresAt: null }),
}));
