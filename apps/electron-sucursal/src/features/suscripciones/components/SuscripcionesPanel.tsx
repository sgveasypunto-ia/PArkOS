/**
 * `<SuscripcionesPanel />` — F9.2 dashboard section.
 *
 * Lists suscripciones for the active branch and exposes a banner per
 * plate when one is approaching expiry. Uses `useSuscripcionesList`
 * (REQ-OPS-132 fetcher-closure) — key gate: `null` when
 * `uuid_sucursal` is empty.
 */
import { useTranslation } from 'react-i18next';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { useSuscripcionesList } from '../hooks/useSuscripcionesList';

export interface SuscripcionesPanelProps {
  uuid_sucursal: string | null;
}

export function SuscripcionesPanel({
  uuid_sucursal,
}: SuscripcionesPanelProps): JSX.Element {
  const { t } = useTranslation('suscripciones');
  const { data: suscripciones, error } = useSuscripcionesList(uuid_sucursal);

  return (
    <div className="space-y-4" data-testid="suscripciones-panel">
      <header className="space-y-1">
        <h3 className="text-lg font-semibold">
          {t('titulo', { defaultValue: 'Suscripciones' })}
        </h3>
      </header>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {t('error', { defaultValue: 'Error al cargar suscripciones' })}
        </p>
      )}

      {suscripciones && suscripciones.length === 0 && (
        <p className="text-sm text-muted-foreground" role="status">
          {t('vacio', { defaultValue: 'Sin suscripciones activas.' })}
        </p>
      )}

      {suscripciones && suscripciones.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('titulo', { defaultValue: 'Suscripciones' })}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm" data-testid="suscripciones-list">
              {suscripciones.map((s) => (
                <li key={s.uuid} className="flex items-center justify-between">
                  <span className="font-mono">{s.placa}</span>
                  <span className="text-muted-foreground">
                    {s.estado === 'activa' ? t('activa', { defaultValue: 'Activa' }) : t('vencida', { defaultValue: 'Vencida' })}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}