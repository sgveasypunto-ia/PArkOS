/**
 * `apiStatusStore.test.ts` — Strict-TDD RED scaffold for HU-F11.1
 * (REQ-OPS-173 + DA-F11.1-3 threshold-storage).
 *
 * Coverage (verbatim tasks.md §C1.1):
 *   A1: `incrementFailure()` raises `consecutiveFailures` and stamps
 *       `lastFailureIso` with a fresh ISO 8601 timestamp.
 *   A2: `reset()` zeroes the counter AND clears `lastFailureIso`.
 *   A3: `selectApiStatusDown` returns `true` exactly when
 *       `consecutiveFailures >= LOCAL_API_DOWN_THRESHOLD` (3) — the
 *       threshold MUST be exported as a const so test pinning is
 *       deterministic.
 *   A4: `markMounted()` / `markUnmounted()` toggle `isMounted` for the
 *       HMR-defensive guard (R-CARRY-3).
 *
 * RED until C2 lands `apps/electron-sucursal/src/state/apiStatusStore.ts`.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  LOCAL_API_DOWN_THRESHOLD,
  selectApiStatusDown,
  useApiStatusStore,
} from '../apiStatusStore';

describe('apiStatusStore — REQ-OPS-173 (HU-F11.1)', () => {
  beforeEach(() => {
    // Reset to canonical initial state between tests so no counter
    // leaks across scenarios.
    useApiStatusStore.setState({
      consecutiveFailures: 0,
      lastFailureIso: null,
      isMounted: false,
    });
  });

  afterEach(() => {
    useApiStatusStore.setState({
      consecutiveFailures: 0,
      lastFailureIso: null,
      isMounted: false,
    });
  });

  it('A1: incrementFailure() raises consecutiveFailures and stamps lastFailureIso with a fresh ISO timestamp', () => {
    const before = useApiStatusStore.getState().consecutiveFailures;
    expect(before).toBe(0);
    expect(useApiStatusStore.getState().lastFailureIso).toBeNull();

    useApiStatusStore.getState().incrementFailure();
    const after = useApiStatusStore.getState();
    expect(after.consecutiveFailures).toBe(1);
    expect(after.lastFailureIso).not.toBeNull();

    // ISO 8601 parse must succeed and be close to wall-clock now.
    const ts = Date.parse(after.lastFailureIso as string);
    expect(Number.isFinite(ts)).toBe(true);
    expect(Math.abs(ts - Date.now())).toBeLessThan(5_000);

    // Two more failures — counter advances monotonically.
    useApiStatusStore.getState().incrementFailure();
    useApiStatusStore.getState().incrementFailure();
    expect(useApiStatusStore.getState().consecutiveFailures).toBe(3);
  });

  it('A2: reset() zeroes the counter AND clears lastFailureIso', () => {
    useApiStatusStore.setState({
      consecutiveFailures: 3,
      lastFailureIso: '2026-09-21T10:00:00.000Z',
    });

    useApiStatusStore.getState().reset();

    const s = useApiStatusStore.getState();
    expect(s.consecutiveFailures).toBe(0);
    expect(s.lastFailureIso).toBeNull();
  });

  it('A3: selectApiStatusDown returns true exactly when consecutiveFailures >= LOCAL_API_DOWN_THRESHOLD (3)', () => {
    expect(LOCAL_API_DOWN_THRESHOLD).toBe(3);

    useApiStatusStore.setState({ consecutiveFailures: 0 });
    expect(selectApiStatusDown(useApiStatusStore.getState())).toBe(false);

    useApiStatusStore.setState({ consecutiveFailures: 2 });
    expect(selectApiStatusDown(useApiStatusStore.getState())).toBe(false);

    useApiStatusStore.setState({ consecutiveFailures: 3 });
    expect(selectApiStatusDown(useApiStatusStore.getState())).toBe(true);

    useApiStatusStore.setState({ consecutiveFailures: 7 });
    expect(selectApiStatusDown(useApiStatusStore.getState())).toBe(true);
  });

  it('A4: markMounted() and markUnmounted() toggle the isMounted HMR-defensive flag (R-CARRY-3)', () => {
    expect(useApiStatusStore.getState().isMounted).toBe(false);

    useApiStatusStore.getState().markMounted();
    expect(useApiStatusStore.getState().isMounted).toBe(true);

    useApiStatusStore.getState().markUnmounted();
    expect(useApiStatusStore.getState().isMounted).toBe(false);
  });
});
