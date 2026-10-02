/**
 * `EstadoReclamoBadge` -- badge for `prod.reclamo.estado`
 * (`recibido | en_investigacion | resuelto | rechazado`,
 * `STATE_MACHINES['reclamo']`). Mirrors `EstadoAnulacionBadge.tsx`.
 */
import { useTranslation } from 'react-i18next';

import { Badge, type BadgeProps } from '@/components/ui/badge';

import type { ReclamoEstado } from '../api/reclamosSchema';

export interface EstadoReclamoBadgeProps {
  estado: ReclamoEstado | null;
}

const ESTADO_BADGE: Record<
  ReclamoEstado,
  { labelKey: string; fallback: string; variant: NonNullable<BadgeProps['variant']> }
> = {
  recibido: { labelKey: 'reclamos.estado.recibido', fallback: 'Recibido', variant: 'warning' },
  en_investigacion: {
    labelKey: 'reclamos.estado.enInvestigacion',
    fallback: 'En investigación',
    variant: 'secondary',
  },
  resuelto: { labelKey: 'reclamos.estado.resuelto', fallback: 'Resuelto', variant: 'success' },
  rechazado: { labelKey: 'reclamos.estado.rechazado', fallback: 'Rechazado', variant: 'destructive' },
};

export function EstadoReclamoBadge({ estado }: EstadoReclamoBadgeProps): JSX.Element {
  const { t } = useTranslation();

  if (estado === null) {
    return (
      <Badge variant="outline" data-testid="estado-reclamo-badge-none">
        {t('reclamos.estado.none', '—')}
      </Badge>
    );
  }

  const badge = ESTADO_BADGE[estado];
  return (
    <Badge variant={badge.variant} data-testid={`estado-reclamo-badge-${estado}`}>
      {t(badge.labelKey, badge.fallback)}
    </Badge>
  );
}
