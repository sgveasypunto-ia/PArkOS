/**
 * `<AlertasTrigger />` — botón compacto del footer que abre el bottom
 * sheet de alertas (`<AlertasSheet />`). No ocupa espacio del área de
 * operación: vive en la fila de cupos.
 *
 * - El conteo sale de `useAlertas().openAlertsCount` (misma key SWR que el
 *   sheet → sin polling adicional).
 * - Con alertas abiertas el acento sigue la severidad más alta presente
 *   (alta → destructive, media → warning, baja → info). Con 0 queda
 *   neutro/silencioso (ghost, sin badge) pero sigue siendo alcanzable.
 */
import { Bell } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Severidad } from '../../../lib/alertas/severity';
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

import { useAlertas } from '../hooks/useAlertas';

export const ALERTAS_TRIGGER_ID = 'alertas-trigger';

const ACCENT: Record<Severidad, string> = {
  alta: 'border-destructive/40 bg-destructive text-destructive-foreground',
  media: 'border-warning/40 bg-warning text-warning-foreground',
  baja: 'border-info/40 bg-info text-info-foreground',
};
const QUIET = 'border-transparent bg-transparent text-muted-foreground hover:bg-muted';

export interface AlertasTriggerProps {
  uuid_sucursal: string | null;
}

export function AlertasTrigger({ uuid_sucursal }: AlertasTriggerProps): JSX.Element | null {
  const { t } = useTranslation(['alertas']);
  const { mergedAlertas, openAlertsCount } = useAlertas(uuid_sucursal);
  const expanded = useDashboardDrawerStore((s) => s.openDrawer === 'alertas');
  const openDrawer = useDashboardDrawerStore((s) => s.open);
  const closeDrawer = useDashboardDrawerStore((s) => s.close);

  // Mismo gate que el panel: sin contexto de sucursal no se pinta nada.
  if (!uuid_sucursal) return null;

  const severidad: Severidad | null =
    openAlertsCount === 0
      ? null
      : mergedAlertas.some((a) => a.severidad === 'alta')
        ? 'alta'
        : mergedAlertas.some((a) => a.severidad === 'media')
          ? 'media'
          : 'baja';

  const label = t('alertas:trigger.label', {
    count: openAlertsCount,
    defaultValue_zero: 'Alertas: ninguna abierta',
    defaultValue_one: 'Alertas: {{count}} abierta',
    defaultValue_other: 'Alertas: {{count}} abiertas',
  });

  return (
    <>
    <button
      type="button"
      id={ALERTAS_TRIGGER_ID}
      data-testid="alertas-trigger"
      data-severidad={severidad ?? 'ninguna'}
      aria-haspopup="dialog"
      aria-expanded={expanded}
      aria-label={label}
      onClick={() => (expanded ? closeDrawer() : openDrawer('alertas', ALERTAS_TRIGGER_ID))}
      className={`inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-semibold uppercase tracking-[0.04em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
        severidad ? ACCENT[severidad] : QUIET
      }`}
    >
      <Bell aria-hidden className="h-3.5 w-3.5" />
      <span aria-hidden>{t('alertas:trigger.texto', { defaultValue: 'Alertas' })}</span>
      {openAlertsCount > 0 && (
        <span
          className="font-mono text-sm tabular-nums"
          data-testid="alertas-trigger-count"
        >
          {openAlertsCount}
        </span>
      )}
    </button>
    {/* El aria-label del botón no se re-anuncia solo: región viva aparte. */}
    <span role="status" className="sr-only" data-testid="alertas-trigger-status">
      {label}
    </span>
    </>
  );
}
