/**
 * `<ProximasVencerBanner />` — dashboard notice for subscriptions close to
 * (or past) their expiry (PT-3). Fed by
 * `GET /clientes/subscripciones/proximas-vencer`; renders nothing while
 * loading or when there is nothing to warn about. The CTA opens the
 * subscriptions drawer, where "Renovar" is offered per row.
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

import { useSuscripcionesProximasVencer } from '../hooks/useSuscripcionesProximasVencer';

export interface ProximasVencerBannerProps {
  uuid_sucursal: string | null;
}

export function ProximasVencerBanner({
  uuid_sucursal,
}: ProximasVencerBannerProps): JSX.Element | null {
  const { t } = useTranslation(['suscripciones']);
  const openDrawer = useDashboardDrawerStore((s) => s.open);
  const { data } = useSuscripcionesProximasVencer(uuid_sucursal);

  if (!data || data.length === 0) return null;

  const vencidas = data.filter((d) => d.vencida).length;
  const proxima = data[0]!;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="proximas-vencer-banner"
      className="flex flex-wrap items-center justify-between gap-2 rounded border border-warning bg-warning px-3 py-2 text-sm font-medium text-warning-foreground"
    >
      <span data-testid="proximas-vencer-banner-texto">
        {t('suscripciones:banner.texto', {
          count: data.length,
          defaultValue_one: '{{count}} suscripción próxima a vencer.',
          defaultValue_other: '{{count}} suscripciones próximas a vencer.',
        })}{' '}
        {vencidas > 0 &&
          t('suscripciones:banner.vencidas', {
            count: vencidas,
            defaultValue_one: '{{count}} ya venció.',
            defaultValue_other: '{{count}} ya vencieron.',
          })}{' '}
        {t('suscripciones:banner.proxima', {
          cliente: proxima.cliente_nombre,
          fecha: proxima.fecha_vencimiento,
          defaultValue: 'La más cercana: {{cliente}} ({{fecha}}).',
        })}
      </span>
      <Button
        type="button"
        size="sm"
        variant="outline"
        data-testid="proximas-vencer-banner-ver"
        onClick={() => openDrawer('suscripciones', 'sidebar-suscripciones')}
      >
        {t('suscripciones:banner.ver', { defaultValue: 'Ver suscripciones' })}
      </Button>
    </div>
  );
}
