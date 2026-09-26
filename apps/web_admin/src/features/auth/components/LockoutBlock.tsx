/**
 * `<LockoutBlock />` — replaces the form's submit area while the
 * account is locked (F3.2 mirror for `web_admin`, IT-1.10).
 *
 * Rendered instead of (or above) the submit button when
 * `accountLockedUntil` is a future Date. Shows a countdown with
 * `<p role="status" aria-live="polite">` so screen readers announce
 * "Cuenta bloqueada, intente en mm:ss" without interrupting the
 * user (polite, not assertive).
 *
 * The countdown itself lives in the parent (`<Login />` container)
 * via `useCountdown`. The block receives the secondsRemaining
 * already-formatted as `mm:ss` plus an `onLockoutExpired` callback
 * to clear the parent state.
 */
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';

export interface LockoutBlockProps {
  formattedRemaining: string;
  className?: string;
}

export function LockoutBlock({ formattedRemaining, className }: LockoutBlockProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <p
      role="status"
      aria-live="polite"
      data-testid="lockout-block"
      className={cn(
        'rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive',
        className,
      )}
    >
      {t('auth.locked')} — {t('auth.retryIn', { remaining: formattedRemaining })}
    </p>
  );
}
