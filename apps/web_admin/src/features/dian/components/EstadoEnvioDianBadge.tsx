/**
 * `EstadoEnvioDianBadge` -- badge for `prod.envio_dian.estado`
 * (`ENVIO_DIAN_ESTADOS`, the confirmed real domain -- see
 * `envioDianSchema.ts`'s docblock). Same semantic-token convention as
 * `alertas/components/EstadoAlertaBadge.tsx`.
 */
import { useTranslation } from 'react-i18next';

import { Badge, type BadgeProps } from '@/components/ui/badge';

import { ENVIO_DIAN_ESTADOS, type EnvioDianEstado } from '../api/envioDianSchema';

export interface EstadoEnvioDianBadgeProps {
  estado: string | null;
}

const ESTADO_BADGE: Record<
  EnvioDianEstado,
  { labelKey: string; fallback: string; variant: NonNullable<BadgeProps['variant']> }
> = {
  pendiente: { labelKey: 'dian.estado.pendiente', fallback: 'Pendiente', variant: 'secondary' },
  enviado: { labelKey: 'dian.estado.enviado', fallback: 'Enviado', variant: 'secondary' },
  en_proceso: { labelKey: 'dian.estado.enProceso', fallback: 'En proceso', variant: 'warning' },
  ack: { labelKey: 'dian.estado.ack', fallback: 'Confirmado (ack)', variant: 'success' },
  aceptado: { labelKey: 'dian.estado.aceptado', fallback: 'Aceptado', variant: 'success' },
  rechazado: { labelKey: 'dian.estado.rechazado', fallback: 'Rechazado', variant: 'destructive' },
  timeout: { labelKey: 'dian.estado.timeout', fallback: 'Timeout', variant: 'destructive' },
  error: { labelKey: 'dian.estado.error', fallback: 'Error', variant: 'destructive' },
};

function isKnownEstado(estado: string): estado is EnvioDianEstado {
  return (ENVIO_DIAN_ESTADOS as readonly string[]).includes(estado);
}

export function EstadoEnvioDianBadge({ estado }: EstadoEnvioDianBadgeProps): JSX.Element {
  const { t } = useTranslation();

  if (estado === null || !isKnownEstado(estado)) {
    return (
      <Badge variant="outline" data-testid="estado-envio-dian-badge-none">
        {t('dian.estado.none', '—')}
      </Badge>
    );
  }

  const badge = ESTADO_BADGE[estado];
  return (
    <Badge variant={badge.variant} data-testid={`estado-envio-dian-badge-${estado}`}>
      {t(badge.labelKey, badge.fallback)}
    </Badge>
  );
}
