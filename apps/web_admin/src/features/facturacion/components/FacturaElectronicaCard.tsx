/**
 * `<FacturaElectronicaCard />` — FE block (REQ-X-07).
 *
 * Three states:
 *   - 200 from `GET /facturacion/factura-electronica/{uuid}`: render the
 *     card with prefijo, consecutivo, estado_dian badge, cufe (visible
 *     ONLY when estado_dian === 'aceptado'), and a "Reintentar" button
 *     visible ONLY when estado_dian === 'rechazado'.
 *   - 404 (no FE row): "Esta factura no tiene FE generada" message.
 *   - 5xx / network: inline error + retry.
 */
import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import type { FacturaElectronicaRead } from '../api/facturacionAdminApi';
import { FacturacionHttpError } from '../api/facturacionAdminApi';

export interface FacturaElectronicaCardProps {
  fe: FacturaElectronicaRead | undefined;
  isLoading: boolean;
  error: Error | null | undefined;
  isRetrying: boolean;
  onRetry: () => void;
  onRetryFe: () => void;
}

const ESTADO_BADGE: Record<
  FacturaElectronicaRead['estado_dian'],
  { labelKey: string; fallback: string; variant: 'secondary' | 'warning' | 'success' | 'destructive' }
> = {
  pendiente: {
    labelKey: 'fe.estadoPendiente',
    fallback: 'Pendiente',
    variant: 'warning',
  },
  enviado: {
    labelKey: 'fe.estadoEnviado',
    fallback: 'Enviado',
    variant: 'secondary',
  },
  aceptado: {
    labelKey: 'fe.estadoAceptado',
    fallback: 'Aceptado',
    variant: 'success',
  },
  rechazado: {
    labelKey: 'fe.estadoRechazado',
    fallback: 'Rechazado',
    variant: 'destructive',
  },
};

export function FacturaElectronicaCard({
  fe,
  isLoading,
  error,
  isRetrying,
  onRetry,
  onRetryFe,
}: FacturaElectronicaCardProps): JSX.Element {
  const { t } = useTranslation('facturacionAdmin');

  // 404 = no FE row (recoverable state, not an error).
  const notFound = error instanceof FacturacionHttpError && error.status === 404;

  return (
    <Card data-testid="factura-fe-card">
      <CardHeader>
        <CardTitle className="text-base">
          {t('fe.title', 'Factura electrónica')}
        </CardTitle>
        <CardDescription>
          {isLoading
            ? t('errors.sectionFail', 'Cargando…')
            : fe
              ? fe.estado_dian
              : notFound
                ? t('fe.noGenerada', 'Esta factura no tiene FE generada.')
                : error
                  ? t('errors.sectionFail', 'No se pudo cargar esta sección.')
                  : '—'}
        </CardDescription>
      </CardHeader>
      {fe ? (
        <CardContent className="grid gap-3 md:grid-cols-3">
          <div className="space-y-1">
            <p className="text-xs uppercase text-muted-foreground">
              {t('fe.prefijo', 'Prefijo')}
            </p>
            <p className="font-mono text-sm" data-testid="factura-fe-prefijo">
              {fe.prefijo ?? '—'}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs uppercase text-muted-foreground">
              {t('fe.consecutivo', 'Consecutivo')}
            </p>
            <p className="text-sm tabular-nums" data-testid="factura-fe-consecutivo">
              {fe.consecutivo ?? '—'}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs uppercase text-muted-foreground">
              {t('fe.estado', 'Estado DIAN')}
            </p>
            <Badge
              variant={ESTADO_BADGE[fe.estado_dian].variant}
              data-testid={`factura-fe-estado-${fe.estado_dian}`}
            >
              {t(ESTADO_BADGE[fe.estado_dian].labelKey, ESTADO_BADGE[fe.estado_dian].fallback)}
            </Badge>
          </div>
          {fe.estado_dian === 'aceptado' && fe.cufe ? (
            <div className="space-y-1 md:col-span-3">
              <p className="text-xs uppercase text-muted-foreground">
                {t('fe.cufe', 'CUFE')}
              </p>
              <p
                className="font-mono text-xs break-all"
                data-testid="factura-fe-cufe"
              >
                {fe.cufe}
              </p>
            </div>
          ) : null}
          {fe.estado_dian === 'rechazado' ? (
            <div className="md:col-span-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onRetryFe}
                disabled={isRetrying}
                data-testid="factura-fe-retry"
              >
                <RefreshCw className="mr-2 h-3.5 w-3.5" aria-hidden />
                {isRetrying
                  ? t('fe.retrying', 'Reintentando…')
                  : t('fe.reintentar', 'Reintentar envío')}
              </Button>
            </div>
          ) : null}
        </CardContent>
      ) : error && !notFound ? (
        <CardContent>
          <p
            role="alert"
            aria-live="assertive"
            data-testid="factura-fe-error"
            className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {t('errors.sectionFail', 'No se pudo cargar esta sección.')}{' '}
            <Button type="button" size="sm" variant="ghost" onClick={onRetry}>
              {t('errors.retry', 'Reintentar')}
            </Button>
          </p>
        </CardContent>
      ) : null}
    </Card>
  );
}
