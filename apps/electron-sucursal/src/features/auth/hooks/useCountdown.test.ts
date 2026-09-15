/**
 * useCountdown — 4 unit tests (vitest + @testing-library/react renderHook).
 *
 * RED → GREEN → REFACTOR coverage (DEC-F3.2-01 drift-resistant hook):
 *   U1: baseline — `Date.now()` returns `retryAfterSeconds` immediately.
 *   U2: cleanup on unmount — `clearInterval` invoked, `onComplete` no fires.
 *   U3: `onComplete` fires when `secondsLeft` reaches 0.
 *   U4: drift resistance — `vi.advanceTimersByTime(2000)` with `retryAfterSeconds=60`
 *       decrements `secondsLeft` by 2 (NOT 1) — wall-clock baseline recomputes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { useCountdown } from './useCountdown';

describe('useCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('U1: baseline Date.now() returns retryAfterSeconds inmediatamente', () => {
    const { result } = renderHook(() => useCountdown(60));
    expect(result.current.secondsLeft).toBe(60);
    expect(result.current.isExpired).toBe(false);
  });

  it('U2: cleanup on unmount — clearInterval invocado + onComplete NO fires', () => {
    const onComplete = vi.fn();
    const { unmount } = renderHook(() => useCountdown(60, { onComplete }));
    unmount();
    act(() => {
      vi.advanceTimersByTime(65_000);
    });
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('U3: onComplete fires cuando secondsLeft llega a 0', () => {
    const onComplete = vi.fn();
    const { result } = renderHook(() => useCountdown(2, { onComplete }));
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(result.current.secondsLeft).toBe(0);
    expect(result.current.isExpired).toBe(true);
    expect(onComplete).toHaveBeenCalledOnce();
  });

  it('U4: drift resistance — decrementa 2 (NO 1) con Date.now() baseline', () => {
    const { result } = renderHook(() => useCountdown(60));
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(result.current.secondsLeft).toBe(58);
  });
});
