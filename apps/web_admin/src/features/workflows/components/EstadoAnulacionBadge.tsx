/**
 * `EstadoAnulacionBadge` -- badge for `prod.anulacion.estado`
 * (`iniciada | autorizada | ejecutada | rechazada`,
 * `STATE_MACHINES['anulacion']`). Same semantic-token convention as
 * `alertas/components/EstadoAlertaBadge.tsx`.
 */
import { useTranslation } from 'react-i18next';

import { Badge, type BadgeProps } from '@/components/ui/badge';

import type { AnulacionEstado } from '../api/anulacionesSchema';

export interface EstadoAnulacionBadgeProps {
  estado: AnulacionEstado | null;
}

const ESTADO_BADGE: Record<
  AnulacionEstado,
  { labelKey: string; fallback: string; variant: NonNullable<BadgeProps['variant']> }
> = {
  iniciada: { labelKey: 'anulaciones.estado.iniciada', fallback: 'Iniciada', variant: 'warning' },
  autorizada: {
    labelKey: 'anulaciones.estado.autorizada',
    fallback: 'Autorizada',
    variant: 'secondary',
  },
  ejecutada: { labelKey: 'anulaciones.estado.ejecutada', fallback: 'Ejecutada', variant: 'success' },
  rechazada: {
    labelKey: 'anulaciones.estado.rechazada',
    fallback: 'Rechazada',
    variant: 'destructive',
  },
};

export function EstadoAnulacionBadge({ estado }: EstadoAnulacionBadgeProps): JSX.Element {
  const { t } = useTranslation();

  if (estado === null) {
    return (
      <Badge variant="outline" data-testid="estado-anulacion-badge-none">
        {t('anulaciones.estado.none', '—')}
      </Badge>
    );
  }

  const badge = ESTADO_BADGE[estado];
  return (
    <Badge variant={badge.variant} data-testid={`estado-anulacion-badge-${estado}`}>
      {t(badge.labelKey, badge.fallback)}
    </Badge>
  );
}
