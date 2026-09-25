/**
 * `<FacturaElectronicaRetryPanel />` — F8.2 dashboard section.
 *
 * Polls `useFacturaElectronica(uuid)` (REQ-OPS-132 fetcher-closure)
 * while the operator has an active pending FE. When
 * `estado_dian === 'rechazado'`, the panel exposes a "Reintentar"
 * button that calls `POST /facturacion/factura-electronica/{uuid}/reintentar`.
 *
 * Lazy-mount: when `uuid_fe` is `null`, the panel issues zero fetches
 * (REQ-OPS-139 cold-Dashboard invariant).
 */
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

import { useFacturaElectronica } from '../hooks/useFacturaElectronica';

export interface FacturaElectronicaRetryPanelProps {
  uuid_fe: string | null;
}

/**
 * F31.3 rediseño — el estado DIAN se anunciaba solo por texto plano
 * (sin diferenciación visual entre aceptado/rechazado/pendiente). Se
 * mapea a los tokens semánticos ya construidos (tokens.css/index.css,
 * AA verificado en ambos temas) — mismo criterio que el resto de la
 * app usa para estados (chip suave, no fill sólido).
 */
function estadoChipClass(estado: string): string {
  if (estado === 'aceptado') return 'bg-success text-success-foreground';
  if (estado === 'rechazado') return 'bg-destructive text-destructive-foreground';
  return 'bg-warning text-warning-foreground';
}

export function FacturaElectronicaRetryPanel({
  uuid_fe,
}: FacturaElectronicaRetryPanelProps): JSX.Element {
  const { t } = useTranslation('facturacion');
  const { data, refresh } = useFacturaElectronica(uuid_fe);

  const handleReintentar = useCallback(async () => {
    if (!uuid_fe) return;
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    await parkosFetch(
      `/api/v1/facturacion/factura-electronica/${uuid_fe}/reintentar`,
      { method: 'POST' },
    );
    await refresh();
  }, [uuid_fe, refresh]);

  return (
    <div className="space-y-4" data-testid="factura-electronica-retry-panel">
      <header className="space-y-1">
        <h3 className="text-lg font-semibold">
          {t('fe.titulo', { defaultValue: 'Factura electrónica' })}
        </h3>
      </header>

      {!uuid_fe && (
        <p className="text-sm text-muted-foreground" role="status">
          {t('fe.estado', { defaultValue: 'Estado DIAN' })}: —
        </p>
      )}

      {uuid_fe && !data && (
        <p className="text-sm text-muted-foreground" role="status">
          {t('fe.pendiente', { defaultValue: 'Pendiente' })}
        </p>
      )}

      {data && (
        <Card>
          <CardHeader>
            <CardTitle>{t('fe.estado', { defaultValue: 'Estado DIAN' })}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p
              data-testid="fe-estado"
              data-estado={data.estado_dian}
              className={`inline-flex items-center rounded-full px-2.5 py-1 text-sm font-medium ${estadoChipClass(data.estado_dian)}`}
            >
              {data.estado_dian === 'aceptado' && t('fe.aceptado', { defaultValue: 'Aceptado' })}
              {data.estado_dian === 'rechazado' && t('fe.rechazado', { defaultValue: 'Rechazado' })}
              {data.estado_dian === 'pendiente' && t('fe.pendiente', { defaultValue: 'Pendiente' })}
              {data.estado_dian === 'no_enviado' && t('fe.pendiente', { defaultValue: 'Pendiente' })}
            </p>
            {data.respuesta_proveedor?.cufe && (
              <p className="break-all text-sm" data-testid="fe-cufe">
                {t('fe.cufe', { defaultValue: 'CUFE' })}: <code className="break-all">{data.respuesta_proveedor.cufe}</code>
              </p>
            )}
            {data.estado_dian === 'rechazado' && (
              <div className="mt-4">
                <Button
                  type="button"
                  onClick={handleReintentar}
                  data-testid="fe-reintentar"
                >
                  {t('fe.reintentar', { defaultValue: 'Reintentar' })}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}