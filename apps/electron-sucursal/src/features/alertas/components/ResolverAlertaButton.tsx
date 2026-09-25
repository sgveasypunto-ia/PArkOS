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
import type { TFunction } from 'i18next';

import type { MergedAlerta } from '../../../lib/api/schemas/alertas';

import { useResolverAlerta, type ResolverError } from '../hooks/useResolverAlerta';

export interface ResolverAlertaButtonProps {
  alert: MergedAlerta;
}

/**
 * F31.3 rediseño: `useResolverAlerta().error` ya existía pero nunca se
 * renderizaba — un 403 `actor_is_target` o un fallo de red fallaban
 * en silencio para el operador. Mapea el discriminated union a copy
 * corta; el estado sigue siendo dueño único de la verdad (mismo
 * criterio documentado en `SuscripcionesSheet.tsx`).
 */
function resolverErrorMessage(error: ResolverError, t: TFunction): string {
  switch (error.kind) {
    case 'actor_is_target':
      return t('alertas:dashboard.resolverError.actorIsTarget', {
        defaultValue: 'No podés marcar como revisada una alerta que vos mismo generaste.',
      });
    case 'network':
      return t('alertas:dashboard.resolverError.network', {
        defaultValue: 'Error de red. Intentá de nuevo.',
      });
    case 'http':
    default:
      return t('alertas:dashboard.resolverError.http', {
        defaultValue: 'No se pudo marcar la alerta como revisada.',
      });
  }
}

export function ResolverAlertaButton({ alert }: ResolverAlertaButtonProps): JSX.Element {
  const { t } = useTranslation();
  const { resolve, isResolving, error } = useResolverAlerta();
  return (
    <>
      <button
        type="button"
        data-testid="resolver-alerta-button"
        data-tipo-alerta={alert.tipo_alerta ?? 'desconocido'}
        aria-label={`marcar-revisada-${alert.tipo_alerta ?? 'desconocido'}`}
        aria-busy={isResolving}
        disabled={isResolving}
        onClick={() => {
          void resolve(alert);
        }}
        className="rounded-md bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground transition-colors hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isResolving
          ? t('alertas:dashboard.resolving', { defaultValue: 'Resolviendo…' })
          : t('alertas:dashboard.markResolved', { defaultValue: 'Marcar revisada' })}
      </button>
      {error && (
        <p
          role="alert"
          data-testid="resolver-alerta-error"
          className="w-full basis-full text-xs text-destructive"
        >
          {resolverErrorMessage(error, t)}
        </p>
      )}
    </>
  );
}
