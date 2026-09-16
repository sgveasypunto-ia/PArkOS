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
  const endTime = Date.now() + retryAfterSeconds * TICK_INTERVAL_MS;
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
