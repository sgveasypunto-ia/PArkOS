/**
 * `<LockoutBlock />` — countdown de cuenta bloqueada, POR FUERA del card.
 *
 * F11.4 follow-up -- el operador reportó que el texto "Cuenta bloqueada
 * temporalmente." estaba DENTRO del card con `text-destructive`
 * (demasiado protagonista, competía con el title). Ahora vive como
 * texto de apoyo AL LADO del card, en gris menos protagonista
 * (`text-muted-foreground`) y centrado — mismo patrón que el
 * `turno-cerrado-exito` banner y el help text del welcome card.
 *
 * El componente se monta SOLO cuando el `<Login />` container
 * detecta `errorState.kind === 'lockout'` (después del fix de PR #39
 * que arregló el bug del state stale de `useCountdown`). Así el
 * initializer function de `useState` corre con `retryAfterSeconds`
 * real desde el primer render — `secondsLeft` arranca en 900 (no en
 * 0) y el countdown decrements visiblemente desde el primer tick.
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
 *     (`<Login />`) resetea `errorState` → el countdown se desmonta.
 *
 * Visualmente:
 *   - `text-muted-foreground` (gris) — feedback secundario, no
 *     destructivo.
 *   - `text-center` — alineado al centro del card (max-w-md).
 *   - `mb-4` — separación del card (que viene abajo).
 *   - `text-sm` — tamaño consistente con los help texts.
 */
import { useTranslation } from 'react-i18next';

import { useCountdown } from '../hooks/useCountdown';

/** Convierte segundos a formato mm:ss. Helper inline. */
function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export interface LockoutBlockProps {
  /** Segundos hasta que el BE libere la cuenta. */
  retryAfterSeconds: number;
  /** Callback invocado cuando el countdown llega a 0. */
  onExpired: () => void;
}

export function LockoutBlock({
  retryAfterSeconds,
  onExpired,
}: LockoutBlockProps): JSX.Element {
  const { t } = useTranslation('auth');
  const { secondsLeft, isExpired } = useCountdown(retryAfterSeconds, {
    onComplete: onExpired,
  });

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
