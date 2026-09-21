/**
 * `ResolverAlertaButton.tsx` — "Marcar revisada" action button
 * (HU-F11.2, REQ-OPS-181 + DEC-SUC-25 + DA-F11.2-2).
 *
 * Calls `useResolverAlerta().resolve(alert)`. Optimistic UI is
 * intentionally disabled — the e2e S3 scenario (REQ-OPS-183)
 * verifies the BACKEND row was persisted via testcontainers
 * Postgres, and a stale optimistic update would mask a failed
 * POST. The button is disabled while `isResolving` is true.
 */
import { useTranslation } from 'react-i18next';

import type { MergedAlerta } from '../../../lib/api/schemas/alertas';

import { useResolverAlerta } from '../hooks/useResolverAlerta';

export interface ResolverAlertaButtonProps {
  alert: MergedAlerta;
}

export function ResolverAlertaButton({ alert }: ResolverAlertaButtonProps): JSX.Element {
  const { t } = useTranslation();
  const { resolve, isResolving } = useResolverAlerta();
  return (
    <button
      type="button"
      data-testid="resolver-alerta-button"
      data-tipo-alerta={alert.tipo_alerta ?? 'desconocido'}
      aria-label={`marcar-revisada-${alert.tipo_alerta ?? 'desconocido'}`}
      disabled={isResolving}
      onClick={() => {
        void resolve(alert);
      }}
      className="rounded-md bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {t('alertas:dashboard.markResolved', { defaultValue: 'Marcar revisada' })}
    </button>
  );
}
