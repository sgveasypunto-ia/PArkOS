/**
 * `apiStatusStore.ts` — Zustand store for local-API availability
 * (REQ-OPS-173 + DA-F11.1-3 explicit-threshold + R-CARRY-3 HMR guard).
 *
 * The `<StatusBar />` poll (F2.3) increments `consecutiveFailures` on
 * every `window.bridge.apiStatus.get()` rejection and resets on success.
 * `<LocalApiDownBanner />` derives its visibility from
 * `selectApiStatusDown(state)` so the 3-strike threshold is the single
 * source of truth — no other component decides independently when the
 * API is "down". This replaces the previous ad-hoc read path inside
 * `<StatusBar />` (DA-F11.1-2 single source of truth).
 *
 * `LOCAL_API_DOWN_THRESHOLD` is exported as a constant so test pinning
 * is deterministic (DA-F11.1-3 explicit threshold).
 */
import { create } from 'zustand';

export const LOCAL_API_DOWN_THRESHOLD = 3 as const;

interface ApiStatusState {
  consecutiveFailures: number;
  lastFailureIso: string | null;
  isMounted: boolean;
}

interface ApiStatusActions {
  incrementFailure: () => void;
  reset: () => void;
  markMounted: () => void;
  markUnmounted: () => void;
}

export type ApiStatusStore = ApiStatusState & ApiStatusActions;

export const useApiStatusStore = create<ApiStatusStore>()((set) => ({
  consecutiveFailures: 0,
  lastFailureIso: null,
  isMounted: false,
  incrementFailure: () =>
    set((s) => ({
      consecutiveFailures: s.consecutiveFailures + 1,
      lastFailureIso: new Date().toISOString(),
    })),
  reset: () => set({ consecutiveFailures: 0, lastFailureIso: null }),
  markMounted: () => set({ isMounted: true }),
  markUnmounted: () => set({ isMounted: false }),
}));

/**
 * Selector helper — returns `true` exactly when the consecutive-failure
 * counter has reached the threshold. The threshold is the gating
 * constant (REQ-OPS-172 + REQ-OPS-173) so all banner decisions route
 * through this one function.
 */
export function selectApiStatusDown(state: ApiStatusState): boolean {
  return state.consecutiveFailures >= LOCAL_API_DOWN_THRESHOLD;
}
