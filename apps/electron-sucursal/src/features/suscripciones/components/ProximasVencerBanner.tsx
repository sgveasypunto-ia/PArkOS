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

  // UX3: the feed is the per-plan alert window (NOT the 10-day renewable list
  // of the drawer), so "por vencer" and "vencidas" are counted apart and the
  // window is named instead of folding expired rows into "próximas a vencer".
  const vencidas = data.filter((d) => d.vencida).length;
  const porVencer = data.length - vencidas;
  const proxima = data[0]!;

  const textoPorVencer = t('suscripciones:banner.porVencer', {
    count: porVencer,
    defaultValue_one: '{{count}} suscripción por vencer',
    defaultValue_other: '{{count}} suscripciones por vencer',
  });
  const resumen =
    porVencer === 0
      ? t('suscripciones:banner.soloVencidas', {
          count: vencidas,
          defaultValue_one: '{{count}} suscripción vencida',
          defaultValue_other: '{{count}} suscripciones vencidas',
        })
      : vencidas === 0
        ? textoPorVencer
        : `${textoPorVencer} ${t('suscripciones:banner.y', { defaultValue: 'y' })} ${t(
            'suscripciones:banner.vencidasCorta',
            {
              count: vencidas,
              defaultValue_one: '{{count}} vencida',
              defaultValue_other: '{{count}} vencidas',
            },
          )}`;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="proximas-vencer-banner"
      className="flex flex-wrap items-center justify-between gap-2 rounded border border-warning bg-warning px-3 py-2 text-sm font-medium text-warning-foreground"
    >
      <span data-testid="proximas-vencer-banner-texto">
        {resumen}{' '}
        {t('suscripciones:banner.ventana', {
          defaultValue: 'en su ventana de alerta.',
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
        className="text-foreground"
        data-testid="proximas-vencer-banner-ver"
        onClick={() => openDrawer('suscripciones', 'sidebar-suscripciones')}
      >
        {t('suscripciones:banner.ver', { defaultValue: 'Ver suscripciones' })}
      </Button>
    </div>
  );
}
