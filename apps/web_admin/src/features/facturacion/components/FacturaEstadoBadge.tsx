/**
 * `<FacturaEstadoBadge />` — presentational badge for
 * `prod.facturas.estado` (closed enum: 'vigente' | 'anulada').
 *
 * Same semantic-token convention as
 * `features/dian/components/EstadoEnvioDianBadge.tsx` and
 * `features/alertas/components/EstadoAlertaBadge.tsx`. The badge text
 * carries the meaning (color is never the only channel — WCAG 2.1 AA).
 *
 * Source of the estado value: `lib/estadoFactura.ts::deriveEstadoFactura`
 * (MVP heuristic from `log_transaccional`). When the BE exposes
 * `V_FACTURA_ESTADO` as a real endpoint, swap the prop for the direct
 * read; the badge itself is unchanged.
 */
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import type { FacturaEstado } from '../lib/estadoFactura';

export interface FacturaEstadoBadgeProps {
  estado: FacturaEstado;
}

export function FacturaEstadoBadge({ estado }: FacturaEstadoBadgeProps): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');
  return (
    <Badge
      variant={estado === 'vigente' ? 'success' : 'destructive'}
      data-testid={`factura-estado-badge-${estado}`}
    >
      {t(
        estado === 'vigente' ? 'header.estadoVigente' : 'header.estadoAnulada',
        estado === 'vigente' ? 'Vigente' : 'Anulada',
      )}
    </Badge>
  );
}
