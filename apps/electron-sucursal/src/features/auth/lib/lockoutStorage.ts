/**
 * `lockoutStorage.ts` — persistencia cliente-side del lockout end-time.
 *
 * F11.4 follow-up -- el operador reportó que el countdown se reinicia
 * cada vez que mueve el mouse (re-mounts del `<LockoutBlock />` por
 * React StrictMode dev, hover effects, refresh de página). La causa
 * raíz: `useCountdown(retryAfterSeconds)` calcula
 * `endTime = Date.now() + retryAfterSeconds * 1000` en CADA render.
 * Cada vez que el componente se re-monta, el initializer del `useState`
 * corre de nuevo con `Date.now()` actualizado → el countdown parece
 * reiniciarse.
 *
 * Solución: persistir el `endTime` del lockout en `localStorage` desde
 * el momento en que el BE nos dice que estamos bloqueados. El
 * `<LockoutBlock>` lee ese endTime en mount y lo pasa a `useCountdown`
 * vía la nueva opción `initialEndTime`. Resultado:
 *
 *   - React StrictMode dev re-mounts → initializer lee del localStorage,
 *     usa el MISMO endTime. Sin reset visual.
 *   - Hover/pointer events que triggerean re-renders → useState
 *     persiste, endTime no cambia.
 *   - Browser refresh → initializer lee del localStorage (mismo tab,
 *     mismo localStorage), countdown continúa desde donde estaba.
 *   - Multi-tab: si el operador abre 2 tabs y la primera dispara el
 *     429, la segunda también lee el mismo endTime (mismo localStorage
 *     origin).
 *   - Cuando el countdown expira → `clearLockoutEndTime()` se llama
 *     en el `useEffect` que observa `isExpired`. El próximo login
 *     empieza con localStorage limpio.
 *
 * Si el localStorage está deshabilitado (modo privado, cuota llena),
 * el `try/catch` degrada gracefulmente a "in-memory only" -- el
 * countdown sigue funcionando para esta sesión pero se resetea al
 * refrescar. Aceptable para ese caso raro.
 */
const STORAGE_KEY = 'parkos.lockout.expiresAt';

/**
 * Lee el lockout end-time persistido. Retorna null si:
 *   - No hay valor guardado (primer lockout)
 *   - El valor guardado ya pasó (stale -- el lockout expiró mientras
 *     la página estaba cerrada, por ejemplo)
 *   - El localStorage no está disponible
 *
 * En el caso "stale", limpia el valor para evitar arrastrar datos
 * muertos.
 */
export function getLockoutEndTime(): number | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    const stored = Number(raw);
    if (!Number.isFinite(stored) || stored <= Date.now()) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return stored;
  } catch {
    return null;
  }
}

/**
 * Persiste el lockout end-time en localStorage. Devuelve el endTime
 * calculado (= Date.now() + retryAfterSeconds * 1000).
 *
 * Idempotent: si el endTime resultante es ANTERIOR al valor ya
 * guardado (por un BE que retorna un retryAfterSeconds menor
 * inesperadamente), NO sobrescribe. El lockout más largo es el
 * autoritativo -- si el BE dice 5min pero el operador tenía un
 * lockout de 15min previo, mantenemos los 15min.
 */
export function setLockoutEndTime(retryAfterSeconds: number): number {
  const newEndTime = Date.now() + retryAfterSeconds * 1000;
  if (typeof window === 'undefined') return newEndTime;
  try {
    const existing = Number(window.localStorage.getItem(STORAGE_KEY) ?? '0');
    if (Number.isFinite(existing) && existing > newEndTime) {
      // El lockout persistido es más largo -- mantenerlo.
      return existing;
    }
    window.localStorage.setItem(STORAGE_KEY, String(newEndTime));
    return newEndTime;
  } catch {
    return newEndTime;
  }
}

/**
 * Limpia el lockout end-time de localStorage. Llamar cuando el
 * countdown llega a 0 (o cuando el operador logra entrar). El
 * siguiente login empieza con localStorage limpio.
 */
export function clearLockoutEndTime(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
