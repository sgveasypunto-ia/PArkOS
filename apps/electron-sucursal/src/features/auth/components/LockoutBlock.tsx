/**
 * `<LockoutBlock />` — countdown de cuenta bloqueada, POR FUERA del card.
 *
 * F11.4 follow-up (persistencia) -- el operador reportó que el countdown
 * se reiniciaba en cada re-mount (React StrictMode dev, hover events,
 * re-renders del parent, e incluso refresh de página). Causa raíz:
 * `useCountdown(retryAfterSeconds)` calcula `endTime = Date.now() +
 * retryAfterSeconds * 1000` en cada render; el initializer del useState
 * solo corre en mount; cada re-mount resetea el countdown visual.
 *
 * Solución: persistir el `endTime` del lockout en localStorage via
 * `lib/lockoutStorage.ts`. El initializer function de useState abajo
 * lee del localStorage en mount. Si hay un endTime válido
 * (futuro), se usa verbatim. Si no (primer lockout o el lockout
 * previo ya expiró), se calcula y guarda uno nuevo. El initializer
 * corre SOLO en mount — los re-renders no lo triggerean.
 *
 * Resultado: el countdown muestra "el tiempo restante desde que el
 * BE nos dijo que estamos bloqueados", sin importar cuántas veces
 * se re-monta el componente o se refresque la página. El
 * `onExpired` callback + `useEffect` limpia el localStorage para
 * que el próximo login empiece limpio.
 *
 * A11y (WCAG 2.1 AA — RNF-022 / DEC-F3.2-06):
 *   - `role="status"` + `aria-live="polite"` anuncian el countdown
 *     sin interrumpir al screen reader.
 *   - `aria-label` describe el contexto completo ("Tiempo restante
 *     para reintentar: mm:ss").
 *   - El mensaje "Cuenta bloqueada temporalmente." NO usa
 *     `role="alert"` porque ya hay un banner persistente arriba (el
 *     `turno-cerrado-exito` también es `role="status"`); un segundo
 *     `role="alert"` competiría por el foco de atención.
 *   - El countdown termina cuando `useCountdown` alcanza
 *     `isExpired=true` → `onExpired` callback → el parent
 *     (`<Login />`) resetea `errorState` → el countdown se desmonta
 *     Y limpia el localStorage.
 *
 * Visualmente:
 *   - `text-muted-foreground` (gris) — feedback secundario, no
 *     destructivo.
 *   - `text-center` — alineado al centro del card (max-w-md).
 *   - `mb-4` — separación del card (que viene abajo).
 *   - `text-sm` — tamaño consistente con los help texts.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useCountdown } from '../hooks/useCountdown';
import {
  getLockoutEndTime,
  setLockoutEndTime,
  clearLockoutEndTime,
} from '../lib/lockoutStorage';

/** Convierte segundos a formato mm:ss. Helper inline. */
function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export interface LockoutBlockProps {
  /** Segundos hasta que el BE libere la cuenta (Retry-After del 429). */
  retryAfterSeconds: number;
  /** Callback invocado cuando el countdown llega a 0. */
  onExpired: () => void;
}

export function LockoutBlock({
  retryAfterSeconds,
  onExpired,
}: LockoutBlockProps): JSX.Element {
  const { t } = useTranslation('auth');

  // Resolver el endTime en MOUNT ONLY. El initializer function de useState
  // corre una vez por mount; cada re-mount lee del localStorage (que
  // persiste a través de re-mounts). Si hay un lockout válido
  // guardado, se usa (incluso si el BE en este submit retornó un valor
  // diferente — el más largo es autoritativo). Si no, se calcula y
  // guarda uno nuevo.
  //
  // NOTA: el side-effect `setLockoutEndTime()` DENTRO del initializer es
  // OK porque solo corre en mount (no en re-renders). TypeScript puede
  // quejarse de side-effects en render pero aquí está garantizado que
  // solo corre una vez.
  const [endTime] = useState<number>(() => {
    const stored = getLockoutEndTime();
    if (stored !== null) {
      return stored;
    }
    return setLockoutEndTime(retryAfterSeconds);
  });

  const { secondsLeft, isExpired } = useCountdown(retryAfterSeconds, {
    onComplete: onExpired,
    initialEndTime: endTime,
  });

  // Limpiar el localStorage cuando el countdown expira. Esto permite que
  // el próximo login empiece con localStorage limpio (no hay stale
  // endTime de un lockout ya expirado).
  useEffect(() => {
    if (isExpired) {
      clearLockoutEndTime();
    }
  }, [isExpired]);

  return (
    <div
      data-testid="login-lockout-block"
      className="mb-4 w-full max-w-md text-center"
    >
      <p
        role="status"
        aria-live="polite"
        data-testid="login-error-lockout"
        className="text-sm text-muted-foreground"
      >
        {t('lockout')}
      </p>
      {!isExpired && (
        <p
          role="status"
          aria-live="polite"
          aria-label={t('lockoutLabel', { time: formatTime(secondsLeft) })}
          data-testid="login-countdown"
          className="text-sm text-muted-foreground mt-1"
        >
          {t('lockoutCountdown', { time: formatTime(secondsLeft) })}
        </p>
      )}
    </div>
  );
}
