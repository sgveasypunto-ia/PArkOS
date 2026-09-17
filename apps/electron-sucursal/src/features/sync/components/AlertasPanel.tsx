/**
 * `<AlertasPanel />` — F11.2 in-dashboard alerts list.
 *
 * Polls `useAlertas()` (REQ-OPS-132 fetcher-closure). Lazy-mount via
 * SWR key gate — `null` when `uuid_sucursal` is empty.
 */
import { useTranslation } from 'react-i18next';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { useAlertas } from '../hooks/useSyncEstado';

export interface AlertasPanelProps {
  uuid_sucursal: string | null;
}

export function AlertasPanel({ uuid_sucursal }: AlertasPanelProps): JSX.Element {
  const { t } = useTranslation(['alertas', 'common']);
  const { data, error } = useAlertas(uuid_sucursal);

  return (
    <div className="space-y-4" data-testid="alertas-panel">
      <header className="space-y-1">
        <h3 className="text-lg font-semibold">
          {t('alertas:titulo', { defaultValue: 'Alertas' })}
        </h3>
      </header>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {t('common:error', { defaultValue: 'Error' })}
        </p>
      )}

      {data && data.length === 0 && (
        <p className="text-sm text-muted-foreground" role="status">
          {t('alertas:vacio', { defaultValue: 'Sin alertas abiertas.' })}
        </p>
      )}

      {data && data.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('alertas:titulo', { defaultValue: 'Alertas' })}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm" data-testid="alertas-list">
              {data.map((a) => (
                <li key={a.uuid} className="flex items-start gap-2">
                  <span className="rounded bg-destructive px-1.5 py-0.5 text-xs font-semibold text-destructive-foreground">
                    {a.tipo_alerta}
                  </span>
                  <span>{a.mensaje}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}