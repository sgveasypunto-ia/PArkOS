/**
 * useCountdown — hook reusable drift-resistant con Date.now() baseline.
 *
 * DEC-F3.2-01 (F3.2): el countdown NUNCA usa accumulator (`secondsLeft--`).
 * Recalcula `secondsLeft` desde wall clock en cada tick para resistir tab
 * inactive + system sleep pauses que pausen `setInterval` (browser throttle).
 * R1 mitigation.
 *
 * Comportamiento:
 *   - `endTime` se captura UNA VEZ en mount (Date.now() + retryAfterSeconds * 1000).
 *   - `secondsLeft` se inicializa con el valor correcto al primer render via
 *     initializer function en `useState`.
 *   - `setInterval(1000)` recalcula remaining desde `Date.now()` cada tick.
 *   - Cleanup en `useEffect` return via `clearInterval(id)`.
 *   - `onComplete` callback fires cuando `remaining === 0` y se clears interval.
 *   - Si `retryAfterSeconds === 0`, `isExpired` es `true` desde el primer render
 *     (form re-enabled inmediato, R7 mitigation).
 *
 * Uso:
 *   - `<LoginForm>` consume `useCountdown(error.retryAfterSeconds)` durante lockout.
 *   - Forward F4.x retry buttons + F11.x sync UI lo consumen.
 */
import { useEffect, useState } from 'react';

export interface UseCountdownOptions {
  /**
   * Callback opcional invocado cuando `secondsLeft` llega a 0.
   * Útil para reset external state (e.g., `errorState` en `<Login />`).
   */
  onComplete?: () => void;
  /**
   * Optional pre-computed end-time (ms epoch). When provided, used
   * verbatim as the countdown target instead of computing
   * `Date.now() + retryAfterSeconds * 1000`. Enables persistence
   * across re-mounts (React StrictMode dev, parent re-renders,
   * browser refresh): the initializer function only runs on mount,
   * and when re-mounted it picks up the persisted value from
   * `localStorage` (handled by the consumer — e.g.,
   * `<LockoutBlock />` via `lib/lockoutStorage`).
   *
   * Without `initialEndTime`, the hook computes `endTime` from
   * `Date.now()` on every mount — fine for one-shot countdowns
   * (logout retries, sync UIs), but wrong for state-bound ones
   * that must persist across re-renders.
   */
  initialEndTime?: number;
}

export interface UseCountdownReturn {
  /** Segundos restantes hasta expiración. 0 = expirado. */
  secondsLeft: number;
  /** True si countdown llegó a 0 (form puede re-habilitarse). */
  isExpired: boolean;
}

const TICK_INTERVAL_MS = 1000;

export function useCountdown(
  retryAfterSeconds: number,
  options?: UseCountdownOptions,
): UseCountdownReturn {
  // El `endTime` se calcula UNA VEZ en mount. Si `options.initialEndTime`
  // está provisto (path del lockout con persistencia en localStorage),
  // se usa verbatim. Si no, se calcula desde `Date.now()` (path
  // one-shot: cotizaciones 15min, sync UI, etc.).
  const endTime =
    options?.initialEndTime ?? Date.now() + retryAfterSeconds * TICK_INTERVAL_MS;
  const [secondsLeft, setSecondsLeft] = useState(() =>
    Math.max(0, Math.ceil((endTime - Date.now()) / TICK_INTERVAL_MS)),
  );
  const [isExpired, setIsExpired] = useState(secondsLeft === 0);

  useEffect(() => {
    if (isExpired) return;
    const id = setInterval(() => {
      const remaining = Math.max(0, Math.ceil((endTime - Date.now()) / TICK_INTERVAL_MS));
      setSecondsLeft(remaining);
      if (remaining === 0) {
        setIsExpired(true);
        options?.onComplete?.();
        clearInterval(id);
      }
    }, TICK_INTERVAL_MS);
    return () => clearInterval(id);
  }, [endTime, isExpired, options]);

  return { secondsLeft, isExpired };
}
