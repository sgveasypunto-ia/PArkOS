/**
 * `useCountdown.ts` — seconds-resolution countdown hook for the lockout
 * countdown in the login form (F3.2 mirror for `web_admin`, IT-1.10).
 *
 * Reusable: any future feature that needs a "wait N seconds" timer can
 * call this hook without re-implementing `setInterval` + cleanup. The
 * hook accepts either a target `Date` or a number of seconds, pauses
 * automatically when the tab is hidden (browser `document.hidden`),
 * and fires `onComplete` exactly once when it crosses zero.
 *
 * Why pause on hidden: when the user backgrounds the tab during a
 * lockout countdown, `setInterval` keeps firing at 1Hz and burns CPU
 * for nothing. The next time the tab is foregrounded the timer
 * resumes from the remaining seconds. This is also WCAG-friendly:
 * screen readers don't keep announcing "X seconds remaining" while
 * the user can't see the page.
 */
import { useEffect, useRef, useState } from 'react';

interface UseCountdownOptions {
  /** Called once when the countdown reaches zero. */
  onComplete?: () => void;
  /** Pause when document is hidden. Defaults to true. */
  pauseOnHidden?: boolean;
}

/**
 * @param target — either a `Date` (countdown until that moment) or a
 *                 number of seconds from now. Re-renders with a new
 *                 target reset the countdown.
 * @returns `secondsRemaining` (number, integer, ≥ 0). `0` means the
 *          countdown has elapsed.
 */
export function useCountdown(
  target: Date | number | null,
  { onComplete, pauseOnHidden = true }: UseCountdownOptions = {},
): number {
  const computeRemaining = (): number => {
    if (target === null) return 0;
    const end = typeof target === 'number' ? Date.now() + target * 1000 : target.getTime();
    return Math.max(0, Math.ceil((end - Date.now()) / 1000));
  };

  const [secondsRemaining, setSecondsRemaining] = useState<number>(computeRemaining);
  const onCompleteRef = useRef(onComplete);

  // Keep the callback ref fresh without re-running the effect.
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    if (target === null) {
      setSecondsRemaining(0);
      return;
    }

    let intervalId: ReturnType<typeof setInterval> | null = null;

    const tick = (): void => {
      const remaining = computeRemaining();
      setSecondsRemaining(remaining);
      if (remaining === 0) {
        if (intervalId !== null) {
          clearInterval(intervalId);
          intervalId = null;
        }
        onCompleteRef.current?.();
      }
    };

    // Initial paint.
    tick();

    intervalId = setInterval(tick, 1000);

    if (pauseOnHidden) {
      const onVisibilityChange = (): void => {
        if (document.hidden) {
          if (intervalId !== null) {
            clearInterval(intervalId);
            intervalId = null;
          }
        } else {
          if (intervalId === null && computeRemaining() > 0) {
            tick();
            intervalId = setInterval(tick, 1000);
          }
        }
      };
      document.addEventListener('visibilitychange', onVisibilityChange);
      return () => {
        if (intervalId !== null) clearInterval(intervalId);
        document.removeEventListener('visibilitychange', onVisibilityChange);
      };
    }

    return () => {
      if (intervalId !== null) clearInterval(intervalId);
    };
    // target and pauseOnHidden are reactive inputs; recompute when either
    // changes. `computeRemaining` closes over the current `target`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, pauseOnHidden]);

  return secondsRemaining;
}

/**
 * Format `secondsRemaining` as `mm:ss` for display. Handles the edge
 * case where the user is reading the page at the exact moment the
 * countdown crosses zero.
 */
export function formatCountdown(secondsRemaining: number): string {
  const total = Math.max(0, Math.floor(secondsRemaining));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}
