/**
 * `EstadoAlertaBadge` -- badge for `prod.alerta.estado`
 * (`abierta | en_revision | resuelta`, `STATE_MACHINES['alerta']`).
 * Same semantic-token convention as `SeverityBadge` / `VigenteBadge`.
 */
import { useTranslation } from 'react-i18next';

import { Badge, type BadgeProps } from '@/components/ui/badge';

import type { AlertaEstado } from '../api/alertasSchema';

export interface EstadoAlertaBadgeProps {
  estado: AlertaEstado | null;
}

const ESTADO_BADGE: Record<
  AlertaEstado,
  { labelKey: string; fallback: string; variant: NonNullable<BadgeProps['variant']> }
> = {
  abierta: { labelKey: 'alertas.estado.abierta', fallback: 'Abierta', variant: 'warning' },
  en_revision: { labelKey: 'alertas.estado.enRevision', fallback: 'En revisión', variant: 'secondary' },
  resuelta: { labelKey: 'alertas.estado.resuelta', fallback: 'Resuelta', variant: 'success' },
};

export function EstadoAlertaBadge({ estado }: EstadoAlertaBadgeProps): JSX.Element {
  const { t } = useTranslation();

  if (estado === null) {
    return (
      <Badge variant="outline" data-testid="estado-alerta-badge-none">
        {t('alertas.estado.none', '—')}
      </Badge>
    );
  }

  const badge = ESTADO_BADGE[estado];
  return (
    <Badge variant={badge.variant} data-testid={`estado-alerta-badge-${estado}`}>
      {t(badge.labelKey, badge.fallback)}
    </Badge>
  );
}
